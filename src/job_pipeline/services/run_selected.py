"""Bulk-action orchestrator for hand-picked jobs.

Chains the last three pipeline stages on a user-selected URL list:

    extract_urls.run(urls=...) -> tailor.run(urls=...) -> applier.apply_one(url) per row

Mirrors ``services.full.run_full`` for the extract+tailor portion and
``services.approval.process`` for the per-URL apply loop (sequential,
random delay between submits, graceful fallback to needs_manual when
auto-apply is disabled or its deps are missing).
"""
from __future__ import annotations

import logging
import random
import time

from job_pipeline.db import get_connection, mark_needs_manual
from job_pipeline.services import applier, extract_urls, tailor

log = logging.getLogger(__name__)

DEFAULT_APPLY_DELAY = (300, 600)


def run_selected(
    urls: list[str],
    tailor_workers: int = 3,
    tailor_min_score: int = 0,
    apply_delay_range: tuple[int, int] = DEFAULT_APPLY_DELAY,
) -> dict:
    """Run extract → tailor → apply on the supplied URLs.

    Args:
        urls: Job URLs to process. Order preserved for the apply loop.
        tailor_workers: Parallel workers for the tailor stage (passed to
            applypilot.run_pipeline).
        tailor_min_score: Floor passed to applypilot. Defaults to 0 so every
            user-selected row gets tailored regardless of score. Isolation is
            preserved by passing the same floor to ``block_other_tailoring``
            so non-selected low-score jobs don't leak into the tailor stage.
        apply_delay_range: ``(min_seconds, max_seconds)`` random sleep between
            successive apply submits. Defaults to 5–10 minutes, matching
            ``approval.process``.

    Returns: dict with per-stage summaries and an ``apply`` list of
    per-URL outcomes. Each apply entry has keys: url, status, applied,
    message.
    """
    log.info("run_selected starting on %d urls", len(urls))
    started = time.time()
    results: dict = {"requested": len(urls)}

    if not urls:
        results["status"] = "no_urls"
        results["elapsed_s"] = 0.0
        return results

    try:
        results["extract_urls"] = extract_urls.run(urls=urls)
    except Exception as e:
        log.exception("run_selected: extract_urls failed")
        results["extract_urls"] = {"status": f"error: {e}"}

    try:
        results["tailor"] = tailor.run(
            urls=urls,
            min_score=tailor_min_score,
            workers=tailor_workers,
            block_floor=tailor_min_score,
            # Match approval.py: user already curated by selecting these
            # rows, so prefer accepting more variation in Gemini's output
            # over rejecting on minor field-validation mismatches.
            validation_mode="lenient",
        )
    except Exception as e:
        log.exception("run_selected: tailor failed")
        results["tailor"] = {"status": f"error: {e}"}

    apply_results: list[dict] = []
    conn = get_connection()
    for i, url in enumerate(urls):
        if i > 0:
            delay = random.randint(*apply_delay_range)
            log.info("run_selected: sleeping %ds before next apply", delay)
            time.sleep(delay)

        result = _apply_one_safe(conn, url)
        apply_results.append(result)
        log.info(
            "run_selected: %d/%d %s -> status=%s applied=%s msg=%s",
            i + 1, len(urls), url[:80],
            result.get("status"), result.get("applied"),
            (result.get("message") or "")[:120],
        )

    results["apply"] = apply_results
    results["elapsed_s"] = round(time.time() - started, 1)
    by_status: dict[str, int] = {}
    for r in apply_results:
        s = r.get("status") or "unknown"
        by_status[s] = by_status.get(s, 0) + 1
    log.info(
        "run_selected done in %.1fs (applied=%d, by_status=%s)",
        results["elapsed_s"],
        sum(1 for r in apply_results if r.get("applied")),
        by_status,
    )
    return results


def _apply_one_safe(conn, url: str) -> dict:
    """Wrap ``applier.apply_one`` to mirror approval._apply_single fallbacks.

    Catches AutoApplyDisabled / MissingDependency and marks the row
    needs_manual instead of crashing the loop.
    """
    try:
        result = applier.apply_one(url)
    except applier.AutoApplyDisabled as e:
        mark_needs_manual(conn, url, f"Auto-apply disabled: {e}")
        conn.commit()
        return {
            "url": url,
            "status": "auto_apply_disabled",
            "applied": False,
            "message": str(e),
        }
    except applier.MissingDependency as e:
        log.error("run_selected: missing dep for %s: %s", url, e)
        mark_needs_manual(conn, url, f"Missing dependency: {e}")
        conn.commit()
        return {
            "url": url,
            "status": "missing_dependency",
            "applied": False,
            "message": str(e),
        }

    return {
        "url": url,
        "status": result.get("status", "unknown"),
        "applied": result.get("applied", False),
        "message": result.get("message", ""),
    }

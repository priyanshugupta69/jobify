"""Full daily pipeline orchestrator.

Replaces scripts/daily_pipeline.py main() flow:
  discover + enrich -> cleanup -> score (+ post_score_cleanup)
  -> select top 20 -> extract URLs -> tailor -> send batch.

Each step calls a service module; failures in earlier steps don't block
later ones (matches today's behavior — degraded is better than skipped).
"""
from __future__ import annotations

import logging
import time

from job_pipeline.services import (
    batch,
    cleanup,
    discover,
    extract_urls,
    score,
    tailor,
)

log = logging.getLogger(__name__)

BATCH_SIZE = 20
MIN_SCORE = 8


def run_full() -> dict:
    """Run the complete pipeline from discovery through batch dispatch."""
    log.info("full.run_full starting")
    started = time.time()
    results: dict = {}

    try:
        results["discover"] = discover.run(workers=3)
    except Exception as e:
        log.exception("discover failed")
        results["discover"] = {"status": f"error: {e}"}

    try:
        results["cleanup"] = cleanup.run()
    except Exception as e:
        log.exception("cleanup failed")
        results["cleanup"] = {"status": f"error: {e}"}

    try:
        results["score"] = score.run(run_post_cleanup=True)
    except Exception as e:
        log.exception("score failed")
        results["score"] = {"status": f"error: {e}"}

    selection = batch.select_top(limit=BATCH_SIZE, min_score=MIN_SCORE)
    candidate_urls = [c["url"] for c in selection.get("candidates", [])]
    results["selection"] = {
        "selected": len(candidate_urls),
        "applied_today": selection.get("applied_today"),
        "remaining_today": selection.get("remaining_today"),
        "status": selection.get("status"),
    }

    if not candidate_urls:
        log.info("full.run_full: no candidates after selection — finishing early")
        results["elapsed_s"] = time.time() - started
        return results

    try:
        results["extract_urls"] = extract_urls.run(urls=candidate_urls)
    except Exception as e:
        log.exception("extract_urls failed")
        results["extract_urls"] = {"status": f"error: {e}"}

    try:
        results["tailor"] = tailor.run(urls=candidate_urls, min_score=MIN_SCORE, workers=3)
    except Exception as e:
        log.exception("tailor failed")
        results["tailor"] = {"status": f"error: {e}"}

    try:
        results["batch"] = batch.run(limit=BATCH_SIZE, min_score=MIN_SCORE)
    except Exception as e:
        log.exception("batch failed")
        results["batch"] = {"status": f"error: {e}"}

    results["elapsed_s"] = time.time() - started
    log.info("full.run_full done in %.1fs", results["elapsed_s"])
    return results


def run_batch_only() -> dict:
    """The 'batch-only' variant: skip discover/score, just dispatch the next batch."""
    log.info("full.run_batch_only starting")
    started = time.time()
    return {"batch": batch.run(limit=BATCH_SIZE, min_score=MIN_SCORE),
            "elapsed_s": time.time() - started}

"""Scoring service. Concurrent LLM scoring + post-score cleanup.

Replaces applypilot.pipeline's hard-coded sequential ``run_scoring`` loop
with a ``ThreadPoolExecutor`` over the same per-job primitive
(``applypilot.scoring.scorer.score_job``). Reuses applypilot's prompt,
response parsing, DB query, and LLM client singleton — only the outer
loop is ours.

The shared ``applypilot.llm.LLMClient`` uses a single ``httpx.Client``
that is thread-safe by design and already retries on 429/503 with
``Retry-After``. Vertex token refresh is serialized inside ``google-auth``.
"""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from applypilot.config import RESUME_PATH
from applypilot.database import get_connection, get_jobs_by_stage
from applypilot.scoring.scorer import score_job

from job_pipeline.services import cleanup

log = logging.getLogger(__name__)

DEFAULT_WORKERS = 8


def run(
    workers: int = DEFAULT_WORKERS,
    run_post_cleanup: bool = True,
    limit: int = 0,
) -> dict:
    """Score unscored jobs concurrently, then optionally run post-score cleanup.

    Args:
        workers: Number of parallel LLM workers. Set to 1 for sequential.
        run_post_cleanup: Whether to run cleanup.post_score() after scoring.
        limit: Max jobs to score this run (0 = no limit).

    Returns:
        {elapsed_s, score: {scored, errors, distribution, elapsed}, post_cleanup}
    """
    log.info("score.run starting (workers=%d, limit=%d)", workers, limit)
    started = time.time()

    conn = get_connection()
    jobs = get_jobs_by_stage(conn=conn, stage="pending_score", limit=limit)

    if not jobs:
        log.info("score.run: no pending_score jobs")
        elapsed = time.time() - started
        cleanup_summary = cleanup.post_score() if run_post_cleanup else None
        return {
            "elapsed_s": elapsed,
            "score": {"scored": 0, "errors": 0, "distribution": [], "elapsed": 0.0},
            "post_cleanup": cleanup_summary,
        }

    resume_text = RESUME_PATH.read_text(encoding="utf-8")

    log.info("score.run: scoring %d jobs with %d workers", len(jobs), workers)
    score_t0 = time.time()
    results: list[dict] = []
    errors = 0
    completed = 0
    total = len(jobs)

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="score") as pool:
        futures = {pool.submit(score_job, resume_text, j): j for j in jobs}
        for fut in as_completed(futures):
            job = futures[fut]
            try:
                result = fut.result()
            except Exception as e:
                log.exception("score_job crashed for url=%s", job.get("url", "?"))
                result = {"score": 0, "keywords": "", "reasoning": f"crashed: {e}"}

            result["url"] = job["url"]
            results.append(result)
            completed += 1
            if result["score"] == 0:
                errors += 1

            log.info(
                "[%d/%d] score=%d  %s",
                completed, total, result["score"], (job.get("title") or "?")[:60],
            )

    score_elapsed = time.time() - score_t0
    rate = len(results) / score_elapsed if score_elapsed > 0 else 0
    log.info(
        "score.run: %d scored in %.1fs (%.1f jobs/sec, %d errors)",
        len(results), score_elapsed, rate, errors,
    )

    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        "UPDATE jobs SET fit_score = ?, score_reasoning = ?, scored_at = ? WHERE url = ?",
        [(r["score"], f"{r['keywords']}\n{r['reasoning']}", now, r["url"]) for r in results],
    )
    conn.commit()

    dist_rows = conn.execute(
        "SELECT fit_score, COUNT(*) FROM jobs WHERE fit_score IS NOT NULL "
        "GROUP BY fit_score ORDER BY fit_score DESC"
    ).fetchall()
    distribution = [(row[0], row[1]) for row in dist_rows]

    cleanup_summary = cleanup.post_score() if run_post_cleanup else None
    elapsed = time.time() - started
    log.info("score.run done in %.1fs", elapsed)

    return {
        "elapsed_s": elapsed,
        "score": {
            "scored": len(results),
            "errors": errors,
            "distribution": distribution,
            "elapsed": score_elapsed,
        },
        "post_cleanup": cleanup_summary,
    }

"""Scoring service. Wraps applypilot.pipeline.run_pipeline + post-score cleanup."""
from __future__ import annotations

import logging
import time

from applypilot.pipeline import run_pipeline

from job_pipeline.services import cleanup

log = logging.getLogger(__name__)


def run(validation_mode: str = "lenient", run_post_cleanup: bool = True) -> dict:
    """Score unscored jobs, then optionally run the post-score cleanup pass."""
    log.info("score.run starting")
    started = time.time()
    result = run_pipeline(stages=["score"], validation_mode=validation_mode)
    cleanup_summary: dict | None = None
    if run_post_cleanup:
        cleanup_summary = cleanup.post_score()
    elapsed = time.time() - started
    log.info("score.run done in %.1fs", elapsed)
    return {
        "elapsed_s": elapsed,
        "score": result,
        "post_cleanup": cleanup_summary,
    }

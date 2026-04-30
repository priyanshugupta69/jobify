"""Tailor + cover letter + PDF generation.

Ports the ``tailor_attempts=99`` block-other-jobs workaround from
scripts/daily_pipeline.py::step_tailor: temporarily exclude all
high-fit jobs except the supplied URLs, run applypilot's tailor/cover/pdf
stages, then reset the column.
"""
from __future__ import annotations

import logging
import time

from applypilot.pipeline import run_pipeline

from job_pipeline.db import block_other_tailoring, get_connection, unblock_tailoring

log = logging.getLogger(__name__)


def run(urls: list[str] | None = None, min_score: int = 8, workers: int = 3) -> dict:
    """Tailor resumes, generate cover letters, convert to PDF.

    If ``urls`` is supplied, only those jobs are tailored (others are
    temporarily blocked via the tailor_attempts=99 workaround). If None,
    all eligible jobs are tailored normally.
    """
    log.info("tailor.run starting (urls=%d, min_score=%d)", len(urls or []), min_score)
    started = time.time()
    blocked = 0
    if urls:
        with get_connection() as conn:
            blocked = block_other_tailoring(conn, urls)
            conn.commit()
        log.info("tailor.run blocked %d other jobs", blocked)

    try:
        result = run_pipeline(
            stages=["tailor", "cover", "pdf"],
            min_score=min_score,
            workers=workers,
            validation_mode="normal",
        )
    finally:
        if urls:
            with get_connection() as conn:
                unblocked = unblock_tailoring(conn)
                conn.commit()
            log.info("tailor.run unblocked %d jobs", unblocked)

    elapsed = time.time() - started
    log.info("tailor.run done in %.1fs", elapsed)
    return {"elapsed_s": elapsed, "blocked_others": blocked, **result}

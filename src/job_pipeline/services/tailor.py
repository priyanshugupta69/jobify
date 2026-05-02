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


def run(
    urls: list[str] | None = None,
    min_score: int = 8,
    workers: int = 3,
    block_floor: int | None = None,
    validation_mode: str = "normal",
) -> dict:
    """Tailor resumes, generate cover letters, convert to PDF.

    If ``urls`` is supplied, only those jobs are tailored (others are
    temporarily blocked via the tailor_attempts=99 workaround). If None,
    all eligible jobs are tailored normally.

    Args:
        block_floor: Fit-score floor for the block_other_tailoring helper.
            Defaults to ``min_score`` so the block matches what applypilot
            will actually attempt to pick up. Override only if you need to
            block a wider net than the min_score implies.
        validation_mode: applypilot tailor validator strictness — one of
            ``strict`` | ``normal`` | ``lenient``. Defaults to ``normal``
            (the daily-pipeline default). User-curated flows (approval,
            run_selected) typically pass ``lenient`` because the user
            already made the human-judgement call by picking the job.
    """
    log.info(
        "tailor.run starting (urls=%d, min_score=%d, validation=%s)",
        len(urls or []), min_score, validation_mode,
    )
    started = time.time()
    blocked = 0
    floor = min_score if block_floor is None else block_floor
    if urls:
        with get_connection() as conn:
            blocked = block_other_tailoring(conn, urls, fit_score_floor=floor)
            conn.commit()
        log.info("tailor.run blocked %d other jobs (floor=%d)", blocked, floor)

    try:
        result = run_pipeline(
            stages=["tailor", "cover", "pdf"],
            min_score=min_score,
            workers=workers,
            validation_mode=validation_mode,
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

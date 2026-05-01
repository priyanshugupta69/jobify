"""Pipeline trigger endpoints.

Heavy stages (discover/score/tailor/extract-urls/full) return 202 with
the work happening on FastAPI's threadpool via BackgroundTasks. Light
stages (cleanup/batch/report) run synchronously and return the result.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Body
from pydantic import BaseModel

from job_pipeline.models import PipelineRunResponse
from job_pipeline.services import (
    applier,
    approval,
    batch,
    cleanup,
    discover,
    extract_urls,
    full,
    report,
    score,
    tailor,
)

router = APIRouter(prefix="/pipeline", tags=["pipeline"])
log = logging.getLogger(__name__)


def _wrap(name: str, fn, /, *args, **kwargs):
    try:
        log.info("background[%s] start", name)
        result = fn(*args, **kwargs)
        log.info("background[%s] done", name)
        return result
    except Exception:
        log.exception("background[%s] crashed", name)


# ── Async-style heavy stages ─────────────────────────────────────────────────

@router.post("/discover", response_model=PipelineRunResponse, status_code=202)
def trigger_discover(bg: BackgroundTasks, workers: int = 3) -> PipelineRunResponse:
    bg.add_task(_wrap, "discover", discover.run, workers=workers)
    return PipelineRunResponse(stage="discover", detail="started in background")


@router.post("/score", response_model=PipelineRunResponse, status_code=202)
def trigger_score(bg: BackgroundTasks, workers: int = 8) -> PipelineRunResponse:
    bg.add_task(_wrap, "score", score.run, workers=workers)
    return PipelineRunResponse(stage="score", detail="started in background")


@router.post("/tailor", response_model=PipelineRunResponse, status_code=202)
def trigger_tailor(
    bg: BackgroundTasks,
    body: dict = Body(default_factory=dict),
) -> PipelineRunResponse:
    urls = body.get("urls")
    min_score = int(body.get("min_score", 8))
    workers = int(body.get("workers", 3))
    bg.add_task(_wrap, "tailor", tailor.run, urls=urls, min_score=min_score, workers=workers)
    return PipelineRunResponse(stage="tailor", detail="started in background")


@router.post("/extract-urls", response_model=PipelineRunResponse, status_code=202)
def trigger_extract_urls(
    bg: BackgroundTasks,
    body: dict = Body(default_factory=dict),
) -> PipelineRunResponse:
    urls = body.get("urls")
    limit = int(body.get("limit", 50))
    bg.add_task(_wrap, "extract_urls", extract_urls.run, limit=limit, urls=urls)
    return PipelineRunResponse(stage="extract-urls", detail="started in background")


@router.post("/full", response_model=PipelineRunResponse, status_code=202)
def trigger_full(bg: BackgroundTasks) -> PipelineRunResponse:
    bg.add_task(_wrap, "full", full.run_full)
    return PipelineRunResponse(stage="full", detail="started in background")


# ── Synchronous light stages ─────────────────────────────────────────────────

@router.post("/cleanup")
def trigger_cleanup() -> dict:
    return cleanup.run()


@router.post("/cleanup/post-score")
def trigger_post_score_cleanup() -> dict:
    return cleanup.post_score()


@router.post("/batch")
def trigger_batch(body: dict = Body(default_factory=dict)) -> dict:
    return batch.run(
        limit=int(body.get("limit", batch.MAX_BATCH)),
        min_score=int(body.get("min_score", batch.MIN_SCORE)),
        skip_send=bool(body.get("skip_send", False)),
    )


# ── Approval handler ─────────────────────────────────────────────────────────

class ApprovalRequest(BaseModel):
    mode: str = "all"  # "all" | "select" | "skip"
    selected: list[int] | None = None


@router.post("/approval")
def trigger_approval(body: ApprovalRequest) -> dict:
    return approval.process(mode=body.mode, selected_indices=body.selected)


# ── Auto-apply (single job, for manual testing) ──────────────────────────────

@router.post("/apply/{url:path}")
def trigger_apply_one(url: str) -> dict:
    """Run auto-apply on a single job by URL.

    Refuses unless AUTO_APPLY_ENABLED=true. Defaults to dry-run; flip
    AUTO_APPLY_DRY_RUN=false to actually click Submit.
    """
    try:
        return applier.apply_one(url)
    except applier.AutoApplyDisabled as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=409, detail=str(e))
    except applier.MissingDependency as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail=str(e))


# ── Report ───────────────────────────────────────────────────────────────────

@router.get("/report/daily")
def daily_report() -> dict:
    return report.build()


@router.post("/report/daily/send")
def daily_report_send() -> dict:
    return report.send_daily()

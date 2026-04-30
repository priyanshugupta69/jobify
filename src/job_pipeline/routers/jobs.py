"""CRUD endpoints for the jobs table."""
from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from job_pipeline.db import (
    delete_by_url,
    delete_low_score,
    delete_skipped,
    get_db,
    get_job_by_url,
    get_jobs_by_stage,
    mark_applied,
    mark_needs_manual,
    update_application_url,
    update_tailored_resume,
)
from job_pipeline.models import (
    ApplicationUrlUpdate,
    DeleteResult,
    Job,
    NeedsManualUpdate,
    PipelineStage,
    TailoredResumeUpdate,
    UpdateResult,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[Job])
def list_jobs(
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    stage: PipelineStage = Query("scored"),
    min_score: int | None = Query(None, ge=1, le=10),
    limit: int = Query(100, ge=1, le=1000),
) -> list[dict]:
    return get_jobs_by_stage(conn, stage=stage, min_score=min_score, limit=limit)


@router.delete("/low-score", response_model=DeleteResult)
def delete_low_score_endpoint(
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    threshold: int = Query(5, ge=1, le=10),
) -> DeleteResult:
    return DeleteResult(deleted=delete_low_score(conn, threshold))


@router.delete("/skipped", response_model=DeleteResult)
def delete_skipped_endpoint(
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> DeleteResult:
    return DeleteResult(deleted=delete_skipped(conn))


@router.get("/{url:path}", response_model=Job)
def get_job(
    url: str,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> dict:
    job = get_job_by_url(conn, url)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job not found: {url}")
    return job


@router.patch("/{url:path}/application-url", response_model=UpdateResult)
def patch_application_url(
    url: str,
    body: ApplicationUrlUpdate,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> UpdateResult:
    ok = update_application_url(conn, url, body.application_url)
    if not ok:
        raise HTTPException(status_code=404, detail=f"job not found: {url}")
    return UpdateResult(updated=True)


@router.patch("/{url:path}/tailored-resume", response_model=UpdateResult)
def patch_tailored_resume(
    url: str,
    body: TailoredResumeUpdate,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> UpdateResult:
    ok = update_tailored_resume(conn, url, body.path)
    if not ok:
        raise HTTPException(status_code=404, detail=f"job not found: {url}")
    return UpdateResult(updated=True)


@router.patch("/{url:path}/needs-manual", response_model=UpdateResult)
def patch_needs_manual(
    url: str,
    body: NeedsManualUpdate,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> UpdateResult:
    ok = mark_needs_manual(conn, url, body.error)
    if not ok:
        raise HTTPException(status_code=404, detail=f"job not found: {url}")
    return UpdateResult(updated=True)


@router.patch("/{url:path}/applied", response_model=UpdateResult)
def patch_applied(
    url: str,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> UpdateResult:
    ok = mark_applied(conn, url)
    if not ok:
        raise HTTPException(status_code=404, detail=f"job not found: {url}")
    return UpdateResult(updated=True)


@router.delete("/{url:path}", response_model=DeleteResult)
def delete_job(
    url: str,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> DeleteResult:
    return DeleteResult(deleted=int(delete_by_url(conn, url)))

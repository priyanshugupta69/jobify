"""CRUD endpoints for the jobs table."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from job_pipeline.settings import settings
from job_pipeline.db import (
    delete_by_url,
    delete_low_score,
    delete_skipped,
    get_db,
    get_job_by_url,
    get_jobs_by_stage,
    mark_applied,
    mark_needs_manual,
    mark_viewed,
    update_application_url,
    update_tailored_resume,
)
from job_pipeline.models import (
    ApplicationUrlUpdate,
    BulkDelete,
    DeleteResult,
    Job,
    NeedsManualUpdate,
    PipelineStage,
    TailoredResumeUpdate,
    UpdateResult,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


_SORT_KEYS: dict[str, tuple[str, bool]] = {
    # name -> (column, reverse_for_desc)
    # ``score``: applypilot's default (fit_score desc, discovered_at desc).
    # Others sort purely by the named timestamp, descending = "most recent first".
    "score": ("", True),  # special-cased: keep applypilot's order
    "newest": ("discovered_at", True),
    "oldest": ("discovered_at", False),
    "recently_scored": ("scored_at", True),
    "recently_tailored": ("tailored_at", True),
    "recently_viewed": ("viewed_at", True),
    "recently_applied": ("applied_at", True),
}


def _apply_sort(rows: list[dict], sort: str) -> list[dict]:
    """Stable sort over post-filter rows. Falls through to applypilot's
    score-default when ``sort='score'`` (the helper's own ORDER BY)."""
    if sort == "score" or sort not in _SORT_KEYS:
        return rows
    column, descending = _SORT_KEYS[sort]
    # Place rows missing the column at the end regardless of direction.
    def _key(r: dict) -> tuple[int, str]:
        v = r.get(column) or ""
        return (0 if v else 1, v)
    rows.sort(key=_key, reverse=descending)
    # The "missing -> end" sentinel inverts under reverse=True; flip it back.
    if descending:
        rows.sort(key=lambda r: 0 if r.get(column) else 1)
    return rows


@router.get("", response_model=list[Job])
def list_jobs(
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    stage: PipelineStage = Query("scored"),
    min_score: int | None = Query(None, ge=1, le=10),
    limit: int = Query(100, ge=1, le=1000),
    site: str | None = Query(None),
    viewed: str | None = Query(None, pattern="^(all|viewed|unviewed)$"),
    sort: str = Query("score", pattern="^(score|newest|oldest|recently_scored|recently_tailored|recently_viewed|recently_applied)$"),
) -> list[dict]:
    """List jobs filtered by stage / min_score / site / viewed, with optional sort.

    ``viewed``: ``unviewed`` → only rows with viewed_at IS NULL,
                ``viewed``   → only rows with viewed_at IS NOT NULL,
                ``all``/None → no filter.

    ``sort``: ``score`` (default — applypilot's fit_score desc, then discovered_at desc),
              ``newest`` / ``oldest`` (by discovered_at),
              ``recently_scored`` / ``recently_tailored`` / ``recently_viewed`` /
              ``recently_applied`` (by the corresponding _at column, desc).
    """
    needs_post_filter = (
        site is not None or (viewed in {"viewed", "unviewed"}) or sort != "score"
    )
    if not needs_post_filter:
        return get_jobs_by_stage(conn, stage=stage, min_score=min_score, limit=limit)

    # Pull a generous superset, filter + sort client-side, then truncate.
    # Keeps the applypilot helper as the single source of truth for stage semantics.
    rows = get_jobs_by_stage(conn, stage=stage, min_score=min_score, limit=0)
    if site is not None:
        site_l = site.lower()
        rows = [r for r in rows if (r.get("site") or "").lower() == site_l]
    if viewed == "unviewed":
        rows = [r for r in rows if not r.get("viewed_at")]
    elif viewed == "viewed":
        rows = [r for r in rows if r.get("viewed_at")]
    rows = _apply_sort(rows, sort)
    return rows[:limit]


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


@router.post("/bulk-delete", response_model=DeleteResult)
def bulk_delete(
    body: BulkDelete,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> DeleteResult:
    deleted = 0
    for url in body.urls:
        if delete_by_url(conn, url):
            deleted += 1
    return DeleteResult(deleted=deleted)


@router.post("/{url:path}/viewed", response_model=UpdateResult)
def mark_viewed_endpoint(
    url: str,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> UpdateResult:
    """Stamp ``viewed_at = now()`` for this job. Fires when the user clicks
    the title link on the dashboard."""
    return UpdateResult(updated=mark_viewed(conn, url))


@router.get("/{url:path}/tailored-resume")
def get_tailored_resume(
    url: str,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
) -> FileResponse:
    job = get_job_by_url(conn, url)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job not found: {url}")
    stored = job.get("tailored_resume_path")
    if not stored:
        raise HTTPException(status_code=404, detail="no tailored resume for this job")

    tailored_dir = (settings.applypilot_dir / "tailored_resumes").resolve()
    # Stored path is the .txt source — the rendered .pdf sits next to it.
    # Fall back to the stored file itself if the PDF is missing.
    candidates = [Path(stored).with_suffix(".pdf"), Path(stored)]
    chosen: Path | None = None
    for c in candidates:
        try:
            resolved = c.resolve()
            resolved.relative_to(tailored_dir)
        except (ValueError, OSError):
            continue
        if resolved.is_file():
            chosen = resolved
            break
    if chosen is None:
        raise HTTPException(status_code=404, detail="resume file not found on disk")

    media_type = "application/pdf" if chosen.suffix == ".pdf" else "text/plain"
    # ``inline`` so the browser renders the PDF / text in the new tab
    # opened by the table's "View" link, instead of silently downloading it.
    return FileResponse(
        chosen,
        media_type=media_type,
        filename=chosen.name,
        content_disposition_type="inline",
    )


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

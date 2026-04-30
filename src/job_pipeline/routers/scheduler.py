"""Scheduler control endpoints."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from job_pipeline.crons import SCHEDULES, by_id

router = APIRouter(prefix="/scheduler", tags=["scheduler"])
log = logging.getLogger(__name__)


@router.get("/jobs")
def list_jobs(request: Request) -> list[dict[str, Any]]:
    """List the active APScheduler jobs (and their next run time)."""
    sched = getattr(request.app.state, "scheduler", None)
    runtime = {j.id: j.next_run_time.isoformat() if j.next_run_time else None
               for j in (sched.get_jobs() if sched else [])}
    return [
        {
            "id": s.id,
            "cron": s.cron,
            "mode": "subprocess" if s.cmd else "direct",
            "cmd": s.cmd,
            "fn": s.fn,
            "timeout": s.timeout,
            "next_run": runtime.get(s.id),
        }
        for s in SCHEDULES
    ]


@router.post("/run/{schedule_id}")
def run_now(schedule_id: str, request: Request) -> dict:
    """Trigger one schedule immediately. Runs through the same target wrapper
    as the cron tick, so timeouts and logging are identical."""
    s = by_id(schedule_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"unknown schedule: {schedule_id}")

    sched = getattr(request.app.state, "scheduler", None)
    if sched is None:
        raise HTTPException(status_code=503, detail="scheduler not running")

    job = sched.get_job(schedule_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job not registered: {schedule_id}")

    job.modify(next_run_time=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))
    return {"id": schedule_id, "triggered": True}

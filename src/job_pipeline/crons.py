"""Cron schedule definitions.

Ports the 7 enabled jobs from ~/.openclaw/cron/jobs.json (UTC). Heavy
stages run as a subprocess via ``python -m job_pipeline.cli`` so we can
hard-kill on timeout (matches OpenClaw's ``timeoutSeconds`` semantics).
Light stages call the service function directly.

The OpenClaw ``memory-cleanup`` job (30 20 * * *) is intentionally NOT
ported — it operates on ~/.openclaw/workspace/, outside this project's
scope. Leave it in OpenClaw cron.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Schedule:
    id: str
    cron: str  # standard 5-field cron expression, UTC
    cmd: list[str] | None  # CLI subcommand to run as subprocess (None = direct call)
    fn: str | None  # dotted path to the function to call directly (None = subprocess)
    timeout: int | None  # seconds; required when cmd is set


SCHEDULES: list[Schedule] = [
    # 6 AM IST — full pipeline. Subprocess for crash isolation + 3h kill.
    Schedule(
        id="job-pipeline-6am",
        cron="30 0 * * *",
        cmd=["full"],
        fn=None,
        timeout=10800,
    ),
    # 10 PM IST daily report.
    Schedule(
        id="job-daily-report",
        cron="30 16 * * *",
        cmd=None,
        fn="job_pipeline.services.report:send_daily",
        timeout=None,
    ),
]


def by_id(schedule_id: str) -> Schedule | None:
    return next((s for s in SCHEDULES if s.id == schedule_id), None)

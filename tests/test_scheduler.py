"""Verify cron entries are registered with the expected schedule."""
from __future__ import annotations

from job_pipeline.crons import SCHEDULES, by_id
from job_pipeline.scheduler import build_scheduler

EXPECTED = {
    "job-pipeline-6am":   ("30 0 * * *",  "subprocess", 10800),
    "job-daily-report":   ("30 16 * * *", "direct",     None),
}


def test_seven_schedules_match_openclaw_cron():
    assert len(SCHEDULES) == len(EXPECTED)
    for sid, (cron, mode, timeout) in EXPECTED.items():
        s = by_id(sid)
        assert s is not None, f"missing schedule: {sid}"
        assert s.cron == cron
        assert ("subprocess" if s.cmd else "direct") == mode
        assert s.timeout == timeout


def test_scheduler_registers_all_jobs():
    sched = build_scheduler()
    try:
        ids = {j.id for j in sched.get_jobs()}
        assert ids == set(EXPECTED.keys())
    finally:
        # Scheduler is not running yet; no shutdown needed
        pass


def test_subprocess_schedule_requires_timeout():
    """Sanity check: any schedule with cmd= must declare a timeout."""
    for s in SCHEDULES:
        if s.cmd is not None:
            assert s.timeout is not None, f"{s.id} has cmd= but no timeout"

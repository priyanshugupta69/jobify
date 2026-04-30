"""APScheduler setup with mixed direct/subprocess execution model.

Light stages run in-process (fast, no risk of hanging). Heavy stages
shell out to ``python -m job_pipeline.cli`` so subprocess.run can hard-
kill on timeout — matches OpenClaw cron's ``timeoutSeconds`` semantics.
"""
from __future__ import annotations

import importlib
import logging
import subprocess
import sys

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from job_pipeline.crons import SCHEDULES, Schedule

log = logging.getLogger(__name__)


def _resolve(fn_path: str):
    module, _, name = fn_path.partition(":")
    if not name:
        module, _, name = fn_path.rpartition(".")
    return getattr(importlib.import_module(module), name)


def _run_subprocess(schedule_id: str, cmd: list[str], timeout: int) -> None:
    log.info("[%s] subprocess start: %s (timeout=%ds)", schedule_id, cmd, timeout)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "job_pipeline.cli", *cmd],
            timeout=timeout,
            capture_output=True,
            text=True,
        )
        log.info("[%s] subprocess done rc=%d", schedule_id, result.returncode)
        if result.returncode != 0:
            log.error("[%s] stderr tail: %s", schedule_id, (result.stderr or "")[-1000:])
    except subprocess.TimeoutExpired:
        log.error("[%s] killed after %ds timeout", schedule_id, timeout)
    except Exception:
        log.exception("[%s] subprocess wrapper crashed", schedule_id)


def _run_direct(schedule_id: str, fn_path: str) -> None:
    log.info("[%s] direct call: %s", schedule_id, fn_path)
    try:
        _resolve(fn_path)()
    except Exception:
        log.exception("[%s] direct call failed", schedule_id)


def _make_target(s: Schedule):
    if s.cmd is not None:
        cmd, timeout, sid = s.cmd, s.timeout, s.id
        assert timeout is not None, f"subprocess schedule {sid} requires a timeout"

        def _target():
            _run_subprocess(sid, cmd, timeout)
        return _target

    fn_path, sid = s.fn, s.id
    assert fn_path is not None, f"schedule {sid} needs cmd or fn"

    def _target():
        _run_direct(sid, fn_path)
    return _target


def build_scheduler() -> BackgroundScheduler:
    sched = BackgroundScheduler(
        timezone="UTC",
        job_defaults={
            "max_instances": 1,
            "misfire_grace_time": 300,
            "coalesce": True,
        },
    )
    for s in SCHEDULES:
        sched.add_job(
            _make_target(s),
            CronTrigger.from_crontab(s.cron, timezone="UTC"),
            id=s.id,
            name=s.id,
            replace_existing=True,
        )
    return sched

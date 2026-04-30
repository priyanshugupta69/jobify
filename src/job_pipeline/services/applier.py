"""Auto-apply service: drives applypilot.apply.launcher to actually submit applications.

SAFETY MODEL:
  - Disabled by default. Set ``AUTO_APPLY_ENABLED=true`` in env to enable.
  - When enabled, defaults to dry-run (Claude fills the form but does not click
    Submit). Set ``AUTO_APPLY_DRY_RUN=false`` only after verifying the dry-run
    flow on a real job.
  - Even with both flags off-default, this service will refuse to run on a job
    that lacks ``application_url`` or ``tailored_resume_path``.

EXTERNAL DEPENDENCIES (verified at runtime):
  - ``claude`` CLI in PATH (Claude Code)
  - ``npx`` (for @playwright/mcp browser bridge)
  - Chrome / Chromium binary (CHROME_PATH env var, defaults to Playwright's bundled Chromium)
  - ANTHROPIC_API_KEY in env or ~/.applypilot/.env

The launcher itself lives in ``applypilot.apply.launcher`` — we just wrap it
with project settings, our DB layer, and an explicit "are you sure" gate.
"""
from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path

from job_pipeline.db import get_connection, mark_needs_manual
from job_pipeline.settings import settings

log = logging.getLogger(__name__)


class AutoApplyDisabled(RuntimeError):
    pass


class MissingDependency(RuntimeError):
    pass


def _ensure_dependencies() -> None:
    """Fail fast with a clear message if a required tool is missing."""
    if not shutil.which("claude"):
        raise MissingDependency("`claude` CLI not found in PATH (install Claude Code)")
    if not shutil.which("npx"):
        raise MissingDependency("`npx` not found in PATH (install Node)")
    chrome = settings.chrome_path
    if not chrome or not Path(chrome).exists():
        raise MissingDependency(f"Chrome binary not found at {chrome!r}")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise MissingDependency("ANTHROPIC_API_KEY not set in env")


def _ensure_chrome_path_exposed() -> None:
    """Make sure applypilot's get_chrome_path() finds the binary we configured."""
    if "CHROME_PATH" not in os.environ and settings.chrome_path:
        os.environ["CHROME_PATH"] = settings.chrome_path


def apply_one(url: str, port: int = 9222, worker_id: int = 0) -> dict:
    """Run auto-apply on a single job by URL.

    Returns:
        dict with keys: status, applied, duration_s, dry_run, message.
    """
    if not settings.auto_apply_enabled:
        raise AutoApplyDisabled(
            "AUTO_APPLY_ENABLED is false. Set it to true in ~/.applypilot/.env to opt in."
        )

    _ensure_dependencies()
    _ensure_chrome_path_exposed()

    conn = get_connection()
    row = conn.execute(
        "SELECT url, title, site, application_url, tailored_resume_path, "
        "fit_score, location, full_description, cover_letter_path "
        "FROM jobs WHERE url = ?",
        (url,),
    ).fetchone()
    if not row:
        return {"status": "not_found", "applied": False, "message": f"job not in DB: {url}"}

    job = {k: row[k] for k in row.keys()}
    if not job.get("application_url"):
        return {
            "status": "no_application_url",
            "applied": False,
            "message": "No application_url (LinkedIn Easy Apply or unresolved). Run extract-urls first.",
        }
    if not job.get("tailored_resume_path") or not Path(job["tailored_resume_path"]).exists():
        return {
            "status": "no_tailored_resume",
            "applied": False,
            "message": "No tailored resume on disk. Tailor first.",
        }

    # Lazy import — applypilot.apply pulls in heavy deps + may patch global state.
    from applypilot.apply.launcher import run_job

    dry_run = settings.auto_apply_dry_run
    log.warning(
        "applier.apply_one: %s job=%s (dry_run=%s, model=%s)",
        "DRY-RUN" if dry_run else "LIVE",
        url[:80],
        dry_run,
        settings.auto_apply_model,
    )

    started = time.time()
    try:
        status, duration_ms = run_job(
            job=job,
            port=port,
            worker_id=worker_id,
            model=settings.auto_apply_model,
            dry_run=dry_run,
        )
    except Exception as e:
        log.exception("applier.apply_one crashed for %s", url)
        return {
            "status": f"crashed: {type(e).__name__}",
            "applied": False,
            "duration_s": time.time() - started,
            "dry_run": dry_run,
            "message": str(e)[:300],
        }

    applied = status == "applied" and not dry_run
    if not applied and not dry_run:
        # Match existing convention: failed real submits become 'needs_manual'.
        mark_needs_manual(conn, url, f"Auto-apply: {status}")
        conn.commit()

    return {
        "status": status,
        "applied": applied,
        "duration_s": round(time.time() - started, 1),
        "dry_run": dry_run,
        "message": f"launcher returned status={status}",
    }

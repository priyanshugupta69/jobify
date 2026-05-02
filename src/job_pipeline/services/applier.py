"""Auto-apply service: drives an agent CLI to actually submit applications.

SAFETY MODEL:
  - Disabled by default. Set ``AUTO_APPLY_ENABLED=true`` in env to enable.
  - When enabled, defaults to dry-run (the agent fills the form but does not
    click Submit). Set ``AUTO_APPLY_DRY_RUN=false`` only after verifying the
    dry-run flow on a real job.
  - Even with both flags off-default, this service will refuse to run on a job
    that lacks ``application_url`` or ``tailored_resume_path``.

AGENT CLI (selected by ``APPLY_AGENT``):
  - ``opencode`` (default) — opencode CLI + Vertex Gemini. Auth via
    GOOGLE_APPLICATION_CREDENTIALS / GOOGLE_CLOUD_PROJECT.
  - ``claude`` — applypilot.apply.launcher with Claude Code. Requires
    ``claude`` CLI in PATH and ANTHROPIC_API_KEY.

SHARED DEPENDENCIES (both agents):
  - ``npx`` (for @playwright/mcp browser bridge)
  - Chrome / Chromium binary (CHROME_PATH env var, defaults to Playwright's bundled Chromium)
"""
from __future__ import annotations

import logging
import os
import shutil
import time
from pathlib import Path

from job_pipeline.db import get_connection, mark_needs_manual
from job_pipeline.settings import resolve_chrome_path, settings

log = logging.getLogger(__name__)


def _app_url_invalid(value) -> bool:
    """An application_url is unusable if it's missing, the literal string
    'None'/'null'/'' (a hand-edited cleared value), or a sentinel marker
    written by extract_urls when scraping couldn't resolve a real apply URL
    (e.g. ``___easy_apply___``, ``___unknown___``, ``___auth_failed___``).
    """
    if value is None:
        return True
    s = str(value).strip().lower()
    return (
        s in {"", "none", "null"}
        or (s.startswith("___") and s.endswith("___"))
    )


class AutoApplyDisabled(RuntimeError):
    pass


class MissingDependency(RuntimeError):
    pass


def _ensure_dependencies() -> None:
    """Fail fast with a clear message if a required tool is missing.

    Required tools depend on ``settings.apply_agent``:
      - ``opencode`` (default): the opencode binary + GOOGLE_APPLICATION_CREDENTIALS
      - ``claude``: the claude binary + ANTHROPIC_API_KEY
    """
    if not shutil.which("npx"):
        raise MissingDependency("`npx` not found in PATH (install Node)")
    if not resolve_chrome_path():
        raise MissingDependency(
            "Chrome/Chromium binary not found. Run "
            "'uv run playwright install chromium chromium-headless-shell' "
            "or set CHROME_PATH in ~/.applypilot/.env."
        )

    agent = (settings.apply_agent or "opencode").lower()
    if agent == "claude":
        if not shutil.which("claude"):
            raise MissingDependency(
                "`claude` CLI not found in PATH (install Claude Code), "
                "or switch APPLY_AGENT to `opencode`."
            )
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise MissingDependency("ANTHROPIC_API_KEY not set in env")
    elif agent == "opencode":
        # opencode is invoked either as a global binary (if available) or
        # lazily via `npx -y opencode-ai@latest`. The npx path is the default
        # and matches how Playwright-MCP is launched, so no install is needed.
        has_binary = bool(settings.apply_agent_path or shutil.which("opencode"))
        has_npx = bool(shutil.which("npx"))
        if not (has_binary or has_npx):
            raise MissingDependency(
                "Neither `opencode` nor `npx` found in PATH. Install Node "
                "(`npx` ships with it) or set APPLY_AGENT_PATH in "
                "~/.applypilot/.env."
            )
        # Accept either GOOGLE_APPLICATION_CREDENTIALS (opencode's native name)
        # or VERTEX_SA_KEY (the convention vertex_llm.py already uses in this repo).
        creds = (
            os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
            or os.environ.get("VERTEX_SA_KEY")
        )
        if not creds:
            raise MissingDependency(
                "Vertex service-account key not set. Provide either "
                "GOOGLE_APPLICATION_CREDENTIALS or VERTEX_SA_KEY in "
                "~/.applypilot/.env."
            )
        if not Path(creds).expanduser().is_file():
            raise MissingDependency(
                f"Vertex SA key path {creds!r} is not a readable file."
            )
        if not (os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("VERTEX_PROJECT")):
            raise MissingDependency(
                "Vertex project not set. Provide either GOOGLE_CLOUD_PROJECT "
                "or VERTEX_PROJECT in ~/.applypilot/.env."
            )
    else:
        raise MissingDependency(
            f"Unknown APPLY_AGENT={agent!r}. Use 'opencode' or 'claude'."
        )


def _ensure_chrome_path_exposed() -> None:
    """Make sure applypilot's get_chrome_path() finds the binary we configured."""
    if "CHROME_PATH" not in os.environ:
        resolved = resolve_chrome_path()
        if resolved:
            os.environ["CHROME_PATH"] = resolved


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
    if _app_url_invalid(job.get("application_url")):
        return {
            "status": "no_application_url",
            "applied": False,
            "message": (
                f"application_url is not usable ({job.get('application_url')!r}). "
                "Re-run extract-urls or set it manually."
            ),
        }
    if not job.get("tailored_resume_path") or not Path(job["tailored_resume_path"]).exists():
        return {
            "status": "no_tailored_resume",
            "applied": False,
            "message": "No tailored resume on disk. Tailor first.",
        }

    # Lazy import — both backends pull in heavy deps + may patch global state.
    agent = (settings.apply_agent or "opencode").lower()
    if agent == "claude":
        from applypilot.apply.launcher import run_job
        agent_model = settings.auto_apply_model
    else:
        from job_pipeline.services.apply_opencode import run_job
        agent_model = settings.apply_agent_model

    dry_run = settings.auto_apply_dry_run
    log.warning(
        "applier.apply_one: %s agent=%s job=%s (dry_run=%s, model=%s)",
        "DRY-RUN" if dry_run else "LIVE",
        agent,
        url[:80],
        dry_run,
        agent_model,
    )

    started = time.time()
    try:
        status, duration_ms = run_job(
            job=job,
            port=port,
            worker_id=worker_id,
            model=agent_model,
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

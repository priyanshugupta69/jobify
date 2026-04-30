"""Process King's approval reply for a pending batch.

Ports scripts/process_approval.py. Three modes:
  - "all"     — tailor (in parallel) + apply to every job in the batch
  - "select"  — same, but only the indices the user picked (1-based)
  - "skip"    — discard the batch
"""
from __future__ import annotations

import json
import logging
import random
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from job_pipeline.db import get_connection, mark_needs_manual
from job_pipeline.services.batch import PENDING_FILE
from job_pipeline.settings import settings

log = logging.getLogger(__name__)

TAILORED_DIR = settings.applypilot_dir / "tailored_resumes"
MAX_PARALLEL = 3


def _tailor_single(job_url: str) -> tuple[str, bool, str | None, str | None]:
    try:
        from applypilot.config import RESUME_PATH, load_profile
        from applypilot.scoring.pdf import convert_to_pdf
        from applypilot.scoring.tailor import tailor_resume

        conn = get_connection()
        row = conn.execute(
            "SELECT title, site, location, full_description, description "
            "FROM jobs WHERE url = ?",
            (job_url,),
        ).fetchone()
        if not row:
            return job_url, False, None, "Job not found in DB"

        profile = load_profile()
        resume_text = RESUME_PATH.read_text()
        job = {
            "url": job_url,
            "title": row[0],
            "site": row[1],
            "location": row[2],
            "full_description": row[3] or row[4],
        }

        tailored, report = tailor_resume(
            resume_text, job, profile, max_retries=3, validation_mode="lenient"
        )
        if not tailored or report["status"] == "exhausted_retries":
            return job_url, False, None, f"Tailoring failed: {report['status']}"

        TAILORED_DIR.mkdir(parents=True, exist_ok=True)
        safe_title = re.sub(r"[^\w\s-]", "", row[0] or "")[:50].strip().replace(" ", "_")
        safe_site = re.sub(r"[^\w\s-]", "", row[1] or "")[:20].strip().replace(" ", "_")
        txt_path = TAILORED_DIR / f"{safe_site}_{safe_title}.txt"
        txt_path.write_text(tailored)
        pdf_path = convert_to_pdf(txt_path)

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE jobs SET tailored_resume_path=?, tailored_at=?, "
            "tailor_attempts=COALESCE(tailor_attempts,0)+1 WHERE url=?",
            (str(txt_path), now, job_url),
        )
        conn.commit()

        return job_url, True, str(pdf_path), None
    except Exception as e:
        log.exception("approval._tailor_single crashed on %s", job_url)
        return job_url, False, None, str(e)


def _apply_single(job: dict, conn: sqlite3.Connection) -> tuple[str, bool, str]:
    """Auto-apply via applypilot.apply.launcher.

    Falls back to the old 'mark needs_manual' behavior when:
      - AUTO_APPLY_ENABLED is false (default — opt-in)
      - A required dependency is missing (Chrome, claude CLI, npx, API key)
      - The job lacks a real application_url (e.g. LinkedIn Easy Apply)
      - The tailored resume isn't on disk
    """
    from job_pipeline.services import applier

    try:
        result = applier.apply_one(job["url"])
    except applier.AutoApplyDisabled as e:
        # Pre-flag fallback: behave exactly like the old stub.
        row = conn.execute(
            "SELECT application_url FROM jobs WHERE url = ?", (job["url"],)
        ).fetchone()
        app_url = row[0] if row else None
        if not app_url:
            return job["url"], False, "No application URL (LinkedIn Easy Apply — manual only)"
        mark_needs_manual(conn, job["url"], f"Application URL: {app_url}")
        conn.commit()
        return job["url"], False, f"Auto-apply disabled: {e}"
    except applier.MissingDependency as e:
        log.error("approval._apply_single missing dep: %s", e)
        mark_needs_manual(conn, job["url"], f"Missing dependency: {e}")
        conn.commit()
        return job["url"], False, str(e)

    if result.get("dry_run"):
        # Dry-run: don't mark applied, don't mark needs_manual — leave row untouched.
        return job["url"], False, f"DRY-RUN: launcher status={result.get('status')}"

    return job["url"], result.get("applied", False), result.get("message", "")


def process(
    mode: str = "all",
    selected_indices: list[int] | None = None,
    apply_delay_range: tuple[int, int] = (300, 600),
) -> dict:
    """Process the current pending_batch.json according to ``mode``."""
    if not PENDING_FILE.exists():
        return {"error": "No pending batch found"}

    pending = json.loads(PENDING_FILE.read_text())
    jobs: list[dict] = pending.get("jobs", [])

    if mode == "skip":
        PENDING_FILE.unlink(missing_ok=True)
        return {"skipped": True, "message": "Batch skipped by user."}

    if mode == "select" and selected_indices:
        jobs = [jobs[i - 1] for i in selected_indices if 0 < i <= len(jobs)]
    if not jobs:
        return {"error": "No jobs to process"}

    results = {"tailored": [], "applied": [], "failed": [], "manual": []}

    log.info("approval: tailoring %d resumes (max %d parallel)", len(jobs), MAX_PARALLEL)
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
        futures = {pool.submit(_tailor_single, j["url"]): j for j in jobs}
        for fut in as_completed(futures):
            url, ok, path, err = fut.result()
            j = futures[fut]
            if ok:
                results["tailored"].append({"url": url, "title": j["title"], "pdf": path})
                log.info("  tailored: %s", (j.get("title") or "")[:40])
            else:
                results["failed"].append({"url": url, "title": j["title"], "error": err})
                log.error("  tailor failed: %s — %s", (j.get("title") or "")[:40], err)

    log.info("approval: applying to %d tailored jobs", len(results["tailored"]))
    conn = get_connection()
    for i, item in enumerate(results["tailored"]):
        if i > 0:
            delay = random.randint(*apply_delay_range)
            log.info("  waiting %ds before next application", delay)
            time.sleep(delay)
        job_data = next((j for j in jobs if j["url"] == item["url"]), None)
        if not job_data:
            continue
        url, ok, err = _apply_single(job_data, conn)
        if ok:
            results["applied"].append(item)
        else:
            results["manual"].append({**item, "error": err})

    PENDING_FILE.unlink(missing_ok=True)
    return results

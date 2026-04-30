"""Batch selection + Telegram dispatch.

Consolidates scripts/apply_batch.py (composite-score selection, dealbreaker
filters, pending_batch.json state) and the send-batch step from
scripts/daily_pipeline.py (MarkdownV2 formatting + PDF attachments).
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from job_pipeline.db import get_connection
from job_pipeline.services import telegram

log = logging.getLogger(__name__)

# Defaults match the existing scripts.
PIPELINE_DIR = Path.home() / ".openclaw/workspace/job_pipeline"
PENDING_FILE = PIPELINE_DIR / "pending_batch.json"
MAX_BATCH = 10
MAX_DAILY = 10
MIN_SCORE = 8
PENDING_TTL_HOURS = 12

TITLE_DEALBREAKERS = [
    "intern", "internship", "co-op", "senior director", "vp ", "vice president",
    "chief", "principal", "staff engineer", "distinguished", "architect",
    "10+ years", "8+ years", "7+ years", "6+ years", "5+ years",
]
DESC_DEALBREAKERS = [
    "us citizens only", "must be us citizen", "u.s. citizen",
    "must be authorized to work in the united states",
    "no sponsorship", "clearance required", "security clearance",
    "based in nordics", "based in europe", "based in the uk",
    "based in benelux", "based in dach",
    "this role is based in nordics", "this role is based in europe",
    "eu only", "uk only", "us only", "canada only",
    "benelux, dach, or the uk",
    "office:denmark", "office:sweden", "office:norway",
    "short-term project", "end of april",
]
NON_INDIA_LOCATIONS = [
    "europe", "uk", "united kingdom", "germany", "france",
    "netherlands", "sweden", "denmark", "norway", "canada",
    "new york", "san francisco", "london", "berlin", "paris",
    "portugal", "romania", "estonia", "latvia", "poland",
]


# ── Selection helpers ────────────────────────────────────────────────────────

def _has_dealbreaker(title: str | None, desc: str | None) -> bool:
    title_l = (title or "").lower()
    desc_l = (desc or "").lower()
    return any(kw in title_l for kw in TITLE_DEALBREAKERS) or any(
        kw in desc_l for kw in DESC_DEALBREAKERS
    )


def _check_experience_fit(desc: str | None) -> bool:
    if not desc:
        return True
    lower = desc.lower()
    for pattern in (
        r"(\d+)\s*\+?\s*(?:to|-|–)\s*(\d+)\s*(?:years?|yrs?)",
        r"(\d+)\s*\+\s*(?:years?|yrs?)\s*(?:of\s+)?(?:experience|exp|professional)",
        r"(?:minimum|at least|min)\s*(?:of\s+)?(\d+)\s*(?:years?|yrs?)",
    ):
        m = re.search(pattern, lower)
        if m:
            min_yrs = int(m.group(1))
            if min_yrs >= 6:
                return False
    return True


def _recency_score(discovered_at: str | None) -> int:
    if not discovered_at:
        return 5
    try:
        disc = datetime.fromisoformat(discovered_at.replace("Z", "+00:00"))
        days = (datetime.now(timezone.utc) - disc).days
        return max(1, 10 - days)
    except (ValueError, TypeError):
        return 5


def _composite(fit: int, recency: int) -> float:
    return round(fit * 0.7 + recency * 0.3, 1)


def _applied_today(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM jobs "
        "WHERE applied_at >= date('now') AND apply_status = 'applied'"
    ).fetchone()[0]


def _select_candidates(conn: sqlite3.Connection, min_score: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT url, title, site, location, fit_score, discovered_at,
               description, full_description, application_url, salary,
               tailored_resume_path
          FROM jobs
         WHERE fit_score >= ?
           AND apply_status IS NULL
           AND (apply_error IS NULL OR apply_error = '')
         ORDER BY fit_score DESC
        """,
        (min_score,),
    ).fetchall()
    cols = [c[0] for c in conn.execute("SELECT * FROM jobs LIMIT 0").description]

    out: list[dict] = []
    for row in rows:
        d = dict(zip(cols, row)) if len(cols) == len(row) else {
            "url": row[0], "title": row[1], "site": row[2], "location": row[3],
            "fit_score": row[4], "discovered_at": row[5], "description": row[6],
            "full_description": row[7], "application_url": row[8], "salary": row[9],
            "tailored_resume_path": row[10],
        }
        full = d.get("full_description") or d.get("description") or ""
        if _has_dealbreaker(d.get("title"), full):
            continue
        loc_l = (d.get("location") or "").lower()
        first500 = full[:500].lower()
        if any(
            x in loc_l and "remote" not in loc_l and "remote" not in first500
            for x in NON_INDIA_LOCATIONS
        ):
            continue
        if not _check_experience_fit(full):
            continue
        recency = _recency_score(d.get("discovered_at"))
        out.append(
            {
                "url": d["url"],
                "title": d.get("title"),
                "site": d.get("site"),
                "location": d.get("location") or "Unknown",
                "fit_score": d["fit_score"],
                "salary": d.get("salary"),
                "application_url": d.get("application_url"),
                "discovered_at": d.get("discovered_at"),
                "tailored_resume_path": d.get("tailored_resume_path"),
                "recency_score": recency,
                "composite_score": _composite(d["fit_score"], recency),
            }
        )
    out.sort(key=lambda x: x["composite_score"], reverse=True)
    return out


# ── Public entry points ──────────────────────────────────────────────────────

def select_top(
    limit: int = MAX_BATCH,
    min_score: int = MIN_SCORE,
    enforce_daily_cap: bool = True,
) -> dict:
    """Pick top N unapplied candidates ranked by composite score (70% fit + 30% recency)."""
    conn = get_connection()
    today = _applied_today(conn)
    remaining = MAX_DAILY - today if enforce_daily_cap else limit
    if enforce_daily_cap and remaining <= 0:
        return {"status": "daily_cap_reached", "applied_today": today, "candidates": []}
    candidates = _select_candidates(conn, min_score)
    take = min(limit, remaining, len(candidates))
    return {
        "status": "ok",
        "applied_today": today,
        "remaining_today": remaining,
        "total_candidates": len(candidates),
        "candidates": candidates[:take],
    }


def _existing_pending() -> dict | None:
    if not PENDING_FILE.exists():
        return None
    try:
        pending = json.loads(PENDING_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if pending.get("status") != "pending_approval":
        return None
    try:
        ts = datetime.fromisoformat(pending["timestamp"])
    except (KeyError, ValueError):
        return None
    if datetime.now(timezone.utc) - ts > timedelta(hours=PENDING_TTL_HOURS):
        return None
    return pending


def _format_message(jobs: list[dict], chunk_start: int, total: int, min_score: int) -> str:
    esc = telegram.escape_markdown
    header = (
        f"🎯 *Daily Batch — Top {total} \\(Score {min_score}\\+\\)* "
        f"\\({chunk_start + 1}\\-{chunk_start + len(jobs)}\\)\n\n"
    )
    lines: list[str] = []
    for i, job in enumerate(jobs, start=chunk_start + 1):
        app_url = job.get("application_url") or ""
        if "easy_apply" in app_url:
            method = "Easy Apply"
        elif app_url and not app_url.startswith("___"):
            method = "External ✅"
        else:
            method = "LinkedIn"
        title = esc(job.get("title") or "")
        loc = esc(job.get("location") or "?")
        salary = esc(job.get("salary") or "Not listed")
        url = job["url"]
        lines.append(
            f"{i}\\. ⭐{job['fit_score']} *{title}* — {loc}\n"
            f"   💰 {salary} \\| 🔗 {method}\n"
            f"   🔗 [Job Link]({url})"
        )
    return header + "\n\n".join(lines)


def send_batch(candidates: list[dict], min_score: int = MIN_SCORE) -> dict:
    """Send the supplied candidates to King via Telegram (text + PDF attachments)."""
    if not candidates:
        return {"status": "empty"}

    sent = 0
    chunk_size = 5
    for start in range(0, len(candidates), chunk_size):
        chunk = candidates[start : start + chunk_size]
        msg = _format_message(chunk, start, len(candidates), min_score)
        if start + len(chunk) >= len(candidates):
            msg += (
                "\n\n*Reply with numbers to approve "
                "\\(e\\.g\\. '1,3,5'\\) or 'approve all' or 'skip'*"
            )
        try:
            telegram.send_message(msg)
            sent += 1
            time.sleep(1)
        except Exception as e:
            log.error("batch.send_batch chunk failed: %s", e)
            return {"status": "error", "sent_chunks": sent, "error": str(e)}

    pdf_sent = 0
    for job in candidates:
        path = job.get("tailored_resume_path")
        if not path:
            continue
        pdf_path = Path(path).with_suffix(".pdf")
        if not pdf_path.exists():
            continue
        try:
            telegram.send_document(pdf_path, caption=f"📄 {(job.get('title') or '')[:50]}")
            pdf_sent += 1
            time.sleep(0.5)
        except Exception as e:
            log.error("batch.send_batch pdf failed for %s: %s", job["url"], e)

    return {"status": "ok", "chunks_sent": sent, "pdfs_sent": pdf_sent}


def run(
    limit: int = MAX_BATCH,
    min_score: int = MIN_SCORE,
    skip_send: bool = False,
) -> dict:
    """Full batch flow: pick top N, save pending_batch.json, dispatch to Telegram."""
    pending = _existing_pending()
    if pending:
        log.info("batch.run: existing pending batch #%s — skipping", pending.get("batch_id"))
        return {"status": "pending_exists", "batch_id": pending.get("batch_id")}

    selection = select_top(limit=limit, min_score=min_score)
    if selection["status"] != "ok" or not selection["candidates"]:
        log.info("batch.run: no candidates (status=%s)", selection["status"])
        return selection

    batch_id = int(datetime.now(timezone.utc).strftime("%m%d%H"))
    PIPELINE_DIR.mkdir(parents=True, exist_ok=True)
    PENDING_FILE.write_text(
        json.dumps(
            {
                "batch_id": batch_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "jobs": selection["candidates"],
                "status": "pending_approval",
            },
            indent=2,
        )
    )

    if skip_send:
        return {"status": "ok", "batch_id": batch_id, "sent": False, **selection}

    send_result = send_batch(selection["candidates"], min_score=min_score)
    return {
        "status": "ok",
        "batch_id": batch_id,
        "sent": send_result.get("status") == "ok",
        "send_result": send_result,
        "candidates": selection["candidates"],
    }

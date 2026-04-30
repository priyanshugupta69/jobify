"""Daily summary report. Ports scripts/daily_report.py.

Inline Gmail OAuth call replaces the subprocess-of-subprocess pattern in
the original script. The Gmail token still lives in the workspace dir.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from job_pipeline.db import get_connection
from job_pipeline.services import telegram

log = logging.getLogger(__name__)

GMAIL_TOKEN = Path.home() / ".openclaw/workspace/gmail_token.json"


def _todays_apps() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT title, site, location, apply_status, applied_at, url
          FROM jobs
         WHERE applied_at >= date('now')
         ORDER BY applied_at DESC
        """
    ).fetchall()
    return [
        {"title": r[0], "site": r[1], "location": r[2],
         "status": r[3], "applied_at": r[4], "url": r[5]}
        for r in rows
    ]


def _pipeline_stats() -> dict:
    conn = get_connection()
    g = lambda sql: conn.execute(sql).fetchone()[0]
    return {
        "total_jobs": g("SELECT COUNT(*) FROM jobs"),
        "scored_7plus": g("SELECT COUNT(*) FROM jobs WHERE fit_score >= 7"),
        "tailored": g("SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL"),
        "applied": g("SELECT COUNT(*) FROM jobs WHERE apply_status = 'applied'"),
        "needs_manual": g("SELECT COUNT(*) FROM jobs WHERE apply_status = 'needs_manual'"),
        "failed": g("SELECT COUNT(*) FROM jobs WHERE apply_status = 'failed'"),
        "pending": g(
            "SELECT COUNT(*) FROM jobs WHERE fit_score >= 7 "
            "AND apply_status IS NULL AND tailored_resume_path IS NULL"
        ),
    }


def _check_inbox(max_results: int = 5) -> list[dict]:
    if not GMAIL_TOKEN.exists():
        return []
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(str(GMAIL_TOKEN))
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        query = (
            "(subject:application OR subject:interview OR subject:offer "
            "OR subject:rejected OR subject:\"thank you for applying\" "
            "OR from:noreply) newer_than:1d"
        )
        resp = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=10)
            .execute()
        )
        emails = []
        for msg in resp.get("messages", [])[:max_results]:
            detail = (
                service.users()
                .messages()
                .get(userId="me", id=msg["id"], format="metadata")
                .execute()
            )
            headers = {h["name"]: h["value"] for h in detail["payload"]["headers"]}
            emails.append(
                {
                    "subject": headers.get("Subject", ""),
                    "from": headers.get("From", ""),
                    "date": headers.get("Date", ""),
                }
            )
        return emails
    except Exception as e:
        log.warning("Gmail check failed: %s", e)
        return []


def build() -> dict:
    """Assemble the report data without sending."""
    apps = _todays_apps()
    stats = _pipeline_stats()
    emails = _check_inbox()
    return {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "applications_today": apps,
        "pipeline": stats,
        "inbox": emails,
    }


def format_text(report: dict) -> str:
    """Format the report dict into the same text the old script produced."""
    apps = report["applications_today"]
    stats = report["pipeline"]
    emails = report["inbox"]
    today = datetime.now(timezone.utc).strftime("%B %d, %Y")
    lines = ["📊 **Daily Job Report**", f"📅 {today}", ""]
    if apps:
        lines.append(f"🚀 **Applied today: {len(apps)}**")
        for a in apps:
            emoji = {"applied": "✅", "needs_manual": "📋", "failed": "❌"}.get(a["status"], "❓")
            lines.append(f"  {emoji} {(a['title'] or '')[:40]} @ {a.get('site') or '?'}")
        lines.append("")
    else:
        lines.append("📭 No applications today.")
        lines.append("")
    lines.append("📈 **Pipeline Overview:**")
    lines.append(f"  • Total jobs: {stats['total_jobs']}")
    lines.append(f"  • Score 7+: {stats['scored_7plus']}")
    lines.append(f"  • Resumes tailored: {stats['tailored']}")
    lines.append(f"  • Applied: {stats['applied']}")
    lines.append(f"  • Needs manual: {stats['needs_manual']}")
    lines.append(f"  • Pending (unapplied, 7+): {stats['pending']}")
    lines.append("")
    if emails:
        lines.append("📧 **Inbox updates (job-related):**")
        for em in emails:
            lines.append(f"  • {(em['subject'] or '')[:50]}")
            lines.append(f"    From: {(em['from'] or '')[:40]}")
    else:
        lines.append("📧 No job-related emails today.")
    return "\n".join(lines)


def send_daily() -> dict:
    """Build the report, send to Telegram, return both."""
    report = build()
    text = format_text(report)
    log.info("report.send_daily — applied today: %d", len(report["applications_today"]))
    try:
        telegram.send_message(telegram.escape_markdown(text), parse_mode="MarkdownV2")
        return {"status": "ok", "report": report}
    except Exception as e:
        log.error("Telegram send failed: %s", e)
        return {"status": "telegram_failed", "error": str(e), "report": report}

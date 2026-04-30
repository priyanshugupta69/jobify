"""DB access layer.

Re-exports applypilot.database helpers (single source of truth for the
``jobs`` table) and adds the few queries scripts use that aren't covered
by the helper API.
"""
from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from datetime import datetime, timezone

from applypilot.database import (
    close_connection,
    ensure_columns,
    get_connection,
    get_jobs_by_stage,
    get_stats,
    init_db,
    store_jobs,
)

__all__ = [
    "close_connection",
    "ensure_columns",
    "get_connection",
    "get_jobs_by_stage",
    "get_stats",
    "init_db",
    "store_jobs",
    "get_db",
    "get_job_by_url",
    "update_application_url",
    "update_tailored_resume",
    "mark_needs_manual",
    "mark_applied",
    "block_other_tailoring",
    "unblock_tailoring",
    "delete_low_score",
    "delete_skipped",
    "delete_by_url",
]

log = logging.getLogger(__name__)


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: yields a thread-local connection, commits on success."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return dict(zip(row.keys(), row))


def get_job_by_url(conn: sqlite3.Connection, url: str) -> dict | None:
    row = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
    return _row_to_dict(row)


def update_application_url(
    conn: sqlite3.Connection, url: str, application_url: str | None
) -> bool:
    cur = conn.execute(
        "UPDATE jobs SET application_url = ? WHERE url = ?",
        (application_url, url),
    )
    return cur.rowcount > 0


def update_tailored_resume(conn: sqlite3.Connection, url: str, path: str) -> bool:
    cur = conn.execute(
        """
        UPDATE jobs
           SET tailored_resume_path = ?,
               tailored_at = ?,
               tailor_attempts = COALESCE(tailor_attempts, 0) + 1
         WHERE url = ?
        """,
        (path, datetime.now(timezone.utc).isoformat(), url),
    )
    return cur.rowcount > 0


def mark_needs_manual(conn: sqlite3.Connection, url: str, error: str) -> bool:
    cur = conn.execute(
        """
        UPDATE jobs
           SET apply_status = 'needs_manual',
               apply_error = ?,
               last_attempted_at = ?
         WHERE url = ?
        """,
        (error, datetime.now(timezone.utc).isoformat(), url),
    )
    return cur.rowcount > 0


def mark_applied(conn: sqlite3.Connection, url: str) -> bool:
    cur = conn.execute(
        """
        UPDATE jobs
           SET apply_status = 'applied',
               applied_at = ?
         WHERE url = ?
        """,
        (datetime.now(timezone.utc).isoformat(), url),
    )
    return cur.rowcount > 0


def block_other_tailoring(conn: sqlite3.Connection, allowed_urls: list[str]) -> int:
    """Tailor-attempts=99 trick: blocks all jobs except `allowed_urls` from being
    picked by `applypilot run tailor`. Ports the workaround from
    scripts/daily_pipeline.py and scripts/prepare_batch.py.
    """
    if not allowed_urls:
        cur = conn.execute(
            "UPDATE jobs SET tailor_attempts = 99 "
            "WHERE fit_score >= 8 AND tailored_resume_path IS NULL"
        )
        return cur.rowcount
    placeholders = ",".join(["?"] * len(allowed_urls))
    cur = conn.execute(
        f"UPDATE jobs SET tailor_attempts = 99 "
        f"WHERE fit_score >= 8 AND tailored_resume_path IS NULL "
        f"AND url NOT IN ({placeholders})",
        allowed_urls,
    )
    return cur.rowcount


def unblock_tailoring(conn: sqlite3.Connection) -> int:
    cur = conn.execute("UPDATE jobs SET tailor_attempts = 0 WHERE tailor_attempts = 99")
    return cur.rowcount


def delete_low_score(conn: sqlite3.Connection, threshold: int = 5) -> int:
    cur = conn.execute(
        "DELETE FROM jobs WHERE fit_score IS NOT NULL AND fit_score <= ?",
        (threshold,),
    )
    return cur.rowcount


def delete_skipped(conn: sqlite3.Connection) -> int:
    cur = conn.execute("DELETE FROM jobs WHERE apply_status = 'skipped'")
    return cur.rowcount


def delete_by_url(conn: sqlite3.Connection, url: str) -> bool:
    cur = conn.execute("DELETE FROM jobs WHERE url = ?", (url,))
    return cur.rowcount > 0

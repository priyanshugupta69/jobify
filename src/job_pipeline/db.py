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

from applypilot.config import DB_PATH
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
    "mark_viewed",
    "ensure_viewed_at_column",
    "block_other_tailoring",
    "unblock_tailoring",
    "delete_low_score",
    "delete_skipped",
    "delete_by_url",
]

log = logging.getLogger(__name__)


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: per-request SQLite connection, thread-safe across
    anyio's threadpool (commit/rollback can land on a different thread than
    the one that opened the connection)."""
    conn = sqlite3.connect(str(DB_PATH), timeout=30, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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


def ensure_viewed_at_column(conn: sqlite3.Connection) -> bool:
    """Idempotent migration: add ``viewed_at`` to ``jobs`` if it doesn't exist.

    Owned by this repo (not applypilot). Records when the user opened a job
    posting from the dashboard so we can offer an "unviewed only" filter.
    """
    cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    if "viewed_at" in cols:
        return False
    conn.execute("ALTER TABLE jobs ADD COLUMN viewed_at TEXT")
    conn.commit()
    log.info("DB migration: added viewed_at column to jobs")
    return True


def mark_viewed(conn: sqlite3.Connection, url: str) -> bool:
    """Stamp ``viewed_at`` to now if the row exists. Idempotent at call site —
    we re-stamp on every dashboard click; whoever last opened the job wins."""
    cur = conn.execute(
        "UPDATE jobs SET viewed_at = ? WHERE url = ?",
        (datetime.now(timezone.utc).isoformat(), url),
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


def block_other_tailoring(
    conn: sqlite3.Connection,
    allowed_urls: list[str],
    fit_score_floor: int = 8,
) -> int:
    """Tailor-attempts=99 trick: blocks all jobs except `allowed_urls` from being
    picked by `applypilot run tailor`. Ports the workaround from
    scripts/daily_pipeline.py and scripts/prepare_batch.py.

    Args:
        allowed_urls: URLs to leave un-blocked.
        fit_score_floor: Only block jobs at or above this score. Default 8
            matches the standard pipeline (which calls applypilot with
            min_score=8). Pass 0 when the caller plans to invoke applypilot
            with a lower min_score (e.g. the bulk-action UI where the user
            explicitly picked low-score rows) — otherwise non-selected
            low-score rows would leak into the tailor stage.
    """
    if not allowed_urls:
        cur = conn.execute(
            "UPDATE jobs SET tailor_attempts = 99 "
            "WHERE fit_score >= ? AND tailored_resume_path IS NULL",
            (fit_score_floor,),
        )
        return cur.rowcount
    placeholders = ",".join(["?"] * len(allowed_urls))
    cur = conn.execute(
        f"UPDATE jobs SET tailor_attempts = 99 "
        f"WHERE fit_score >= ? AND tailored_resume_path IS NULL "
        f"AND url NOT IN ({placeholders})",
        (fit_score_floor, *allowed_urls),
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

"""Cleanup service: deletes unqualified jobs.

Ports scripts/cleanup_jobs.py and scripts/post_score_cleanup.py.

- ``run()``      — full filter pass (titles, descriptions, location, CTC, age, skipped, low score)
- ``post_score()`` — narrower pass run right after scoring (interns, wrong-geo, low CTC, low score)
"""
from __future__ import annotations

import logging
import re
import sqlite3

from job_pipeline.db import get_connection

log = logging.getLogger(__name__)

TITLE_DEALBREAKERS = [
    "intern", "internship", "co-op", "senior director", "vp ", "vice president",
    "chief", "principal", "staff engineer", "distinguished", "architect",
    "10+ years", "8+ years", "7+ years", "6+ years", "5+ years",
    "fresher",
    "lead engineer", "lead developer", "engineering manager", "head of",
]

SENIOR_TITLE_KEYWORDS = [
    "senior", "sr.", "sr ", "staff", "lead", "iii", "iv", " 3", " 4",
]

DESC_DEALBREAKERS = [
    "us citizens only", "must be us citizen", "u.s. citizen",
    "must be authorized to work in the united states",
    "no sponsorship", "clearance required", "security clearance",
    "based in nordics", "based in europe", "based in the uk",
    "based in benelux", "based in dach",
    "eu only", "uk only", "us only", "canada only",
    "short-term project",
]

NON_INDIA_LOCATIONS = [
    "europe", "united kingdom", "germany", "france",
    "netherlands", "sweden", "denmark", "norway",
    "new york", "san francisco", "london", "berlin", "paris",
    "portugal", "romania", "estonia", "latvia", "poland",
    "remote, us", "us (remote)",
]

# Used by post_score
LOCATION_BLOCKERS = [
    "must be us citizen", "us citizens only", "u.s. citizen",
    "must be authorized to work in the united states",
    "based in nordics", "based in europe", "based in the uk",
    "based in benelux", "based in dach",
    "this role is based in nordics", "this role is based in europe",
    "eu only", "uk only", "us only", "canada only",
    "benelux, dach, or the uk",
    "clearance required", "security clearance",
    "no remote from india",
]
INTERN_PATTERNS = ["intern", "internship", "co-op"]


def _classify(row: tuple) -> str | None:
    rowid, url, title, site, location, fit_score, desc, full_desc, salary, _ = row
    full = (full_desc or desc or "").lower()
    title_l = (title or "").lower()
    loc_l = (location or "").lower()

    if fit_score is not None and fit_score < 7:
        return "low_score"

    for kw in TITLE_DEALBREAKERS:
        if kw in title_l:
            return f"title_dealbreaker:{kw}"

    for kw in DESC_DEALBREAKERS:
        if kw in full:
            return f"desc_dealbreaker:{kw}"

    for non_india in NON_INDIA_LOCATIONS:
        if non_india in loc_l and "india" not in loc_l and "india" not in full[:500]:
            return f"non_india_location:{non_india}"

    if any(kw in title_l for kw in SENIOR_TITLE_KEYWORDS):
        for pattern in (
            r"(\d+)\+?\s*(?:years|yrs)",
            r"(\d+)\+?\s*(?:years?|yrs?)\s*(?:of)?\s*(?:experience|exp)",
        ):
            m = re.search(pattern, full)
            if m and int(m.group(1)) >= 4:
                return f"senior_high_exp:{m.group(1)}yr"

    if salary:
        m = re.search(r"(\d+)\s*-?\s*(\d+)?\s*lpa", salary.lower())
        if m:
            max_lpa = int(m.group(2) or m.group(1))
            if max_lpa < 15:
                return f"low_ctc:{max_lpa}lpa"

    return None


def run(conn: sqlite3.Connection | None = None) -> dict:
    """Full filter pass — titles, descriptions, location, CTC, age, skipped, low score."""
    if conn is None:
        conn = get_connection()

    rows = conn.execute(
        """
        SELECT rowid, url, title, site, location, fit_score,
               description, full_description, salary, apply_status
          FROM jobs
         WHERE apply_status IS NULL
        """
    ).fetchall()

    to_delete: list[int] = []
    reasons: dict[str, int] = {}
    for row in rows:
        reason = _classify(tuple(row))
        if reason:
            to_delete.append(row[0])
            reasons[reason] = reasons.get(reason, 0) + 1

    skipped = conn.execute("DELETE FROM jobs WHERE apply_status = 'skipped'").rowcount
    if skipped:
        reasons["skipped_by_user"] = skipped

    old = conn.execute(
        """
        DELETE FROM jobs
         WHERE apply_status IS NULL
           AND discovered_at IS NOT NULL
           AND discovered_at < datetime('now', '-3 days')
        """
    ).rowcount
    if old:
        reasons["old_3d+"] = old

    if to_delete:
        placeholders = ",".join(str(r) for r in to_delete)
        conn.execute(f"DELETE FROM jobs WHERE rowid IN ({placeholders})")

    conn.commit()

    remaining = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE apply_status IS NULL"
    ).fetchone()[0]
    applied = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE apply_status = 'applied'"
    ).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

    summary = {
        "deleted": len(to_delete) + skipped + old,
        "filtered": len(to_delete),
        "reasons": reasons,
        "remaining_unapplied": remaining,
        "applied": applied,
        "total": total,
    }
    log.info("cleanup.run: %s", summary)
    return summary


def post_score(conn: sqlite3.Connection | None = None) -> dict:
    """Narrower pass run after scoring — interns, wrong-geo, low CTC, low score."""
    if conn is None:
        conn = get_connection()

    before = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

    low_score = conn.execute(
        "DELETE FROM jobs WHERE fit_score IS NOT NULL AND fit_score <= 5"
    ).rowcount

    intern_count = 0
    rows = conn.execute(
        "SELECT url, title FROM jobs WHERE apply_status IS NULL"
    ).fetchall()
    for url, title in rows:
        title_l = (title or "").lower()
        if any(p in title_l for p in INTERN_PATTERNS):
            conn.execute("DELETE FROM jobs WHERE url = ?", (url,))
            intern_count += 1

    geo_count = 0
    rows = conn.execute(
        "SELECT url, full_description, description FROM jobs WHERE apply_status IS NULL"
    ).fetchall()
    for url, fdesc, desc in rows:
        text = (fdesc or desc or "").lower()
        if any(b in text for b in LOCATION_BLOCKERS):
            conn.execute("DELETE FROM jobs WHERE url = ?", (url,))
            geo_count += 1

    ctc_count = 0
    rows = conn.execute(
        "SELECT url, full_description, description, salary FROM jobs WHERE apply_status IS NULL"
    ).fetchall()
    for url, fdesc, desc, salary in rows:
        combined = (fdesc or desc or "").lower() + " " + (salary or "").lower()
        m = re.search(r"(\d+)\s*[-–to]*\s*(\d+)?\s*lpa", combined)
        if m:
            max_lpa = int(m.group(2) or m.group(1))
            if max_lpa < 15:
                conn.execute("DELETE FROM jobs WHERE url = ?", (url,))
                ctc_count += 1

    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

    summary = {
        "before": before,
        "after": after,
        "deleted": before - after,
        "low_score": low_score,
        "interns": intern_count,
        "wrong_geo": geo_count,
        "low_ctc": ctc_count,
    }
    log.info("cleanup.post_score: %s", summary)
    return summary

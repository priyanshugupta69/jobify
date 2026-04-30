"""DB helper smoke tests."""
from __future__ import annotations

from job_pipeline.db import (
    delete_low_score,
    delete_skipped,
    get_job_by_url,
    mark_applied,
    mark_needs_manual,
    update_application_url,
    update_tailored_resume,
)


def _insert(conn, **fields):
    cols = ",".join(fields.keys())
    placeholders = ",".join("?" * len(fields))
    conn.execute(f"INSERT INTO jobs ({cols}) VALUES ({placeholders})", list(fields.values()))
    conn.commit()


def test_get_job_by_url_returns_none_for_missing(conn):
    assert get_job_by_url(conn, "https://nope") is None


def test_application_url_roundtrip(conn):
    _insert(conn, url="https://x", title="Eng", site="linkedin")
    assert update_application_url(conn, "https://x", "https://apply") is True
    assert get_job_by_url(conn, "https://x")["application_url"] == "https://apply"


def test_update_tailored_resume_increments_attempts(conn):
    _insert(conn, url="https://x", title="Eng")
    update_tailored_resume(conn, "https://x", "/path/to/resume.txt")
    job = get_job_by_url(conn, "https://x")
    assert job["tailored_resume_path"] == "/path/to/resume.txt"
    assert job["tailored_at"] is not None
    assert job["tailor_attempts"] == 1


def test_mark_needs_manual(conn):
    _insert(conn, url="https://x", title="Eng")
    mark_needs_manual(conn, "https://x", "no_apply_url")
    job = get_job_by_url(conn, "https://x")
    assert job["apply_status"] == "needs_manual"
    assert job["apply_error"] == "no_apply_url"


def test_mark_applied(conn):
    _insert(conn, url="https://x", title="Eng")
    mark_applied(conn, "https://x")
    job = get_job_by_url(conn, "https://x")
    assert job["apply_status"] == "applied"
    assert job["applied_at"] is not None


def test_delete_low_score(conn):
    _insert(conn, url="https://a", fit_score=3)
    _insert(conn, url="https://b", fit_score=8)
    deleted = delete_low_score(conn, threshold=5)
    assert deleted == 1
    assert get_job_by_url(conn, "https://a") is None
    assert get_job_by_url(conn, "https://b") is not None


def test_delete_skipped(conn):
    _insert(conn, url="https://a", apply_status="skipped")
    _insert(conn, url="https://b", apply_status="applied")
    assert delete_skipped(conn) == 1
    assert get_job_by_url(conn, "https://a") is None

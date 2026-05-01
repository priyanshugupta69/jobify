"""Verify score.run executes score_job concurrently and bulk-writes results."""
from __future__ import annotations

import threading
import time

from job_pipeline.services import score


def test_score_run_is_concurrent_and_bulk_writes(conn, monkeypatch, tmp_path):
    # Resume read happens via applypilot.config.RESUME_PATH — short-circuit it
    # so we don't depend on a real resume file under APPLYPILOT_DIR.
    fake_resume = tmp_path / "resume.txt"
    fake_resume.write_text("fake resume")
    monkeypatch.setattr(score, "RESUME_PATH", fake_resume)

    # Skip post_score cleanup; it touches unrelated tables.
    monkeypatch.setattr(score.cleanup, "post_score", lambda: {"skipped": True})

    # Insert 12 pending_score rows.
    rows = [
        (f"https://example.com/job/{i}", f"Engineer {i}", "test", "Job desc")
        for i in range(12)
    ]
    conn.executemany(
        "INSERT INTO jobs (url, title, site, full_description) VALUES (?,?,?,?)",
        rows,
    )
    conn.commit()

    # Fake score_job: each call sleeps 0.2s and records when it ran.
    started_at: list[float] = []
    finished_at: list[float] = []
    lock = threading.Lock()

    def fake_score_job(resume_text, job):
        assert resume_text == "fake resume"
        with lock:
            started_at.append(time.time())
        time.sleep(0.2)
        with lock:
            finished_at.append(time.time())
        # Score = position-derived so we can verify each row got its own value.
        idx = int(job["url"].rsplit("/", 1)[-1])
        return {"score": (idx % 10) + 1, "keywords": f"kw{idx}", "reasoning": f"r{idx}"}

    monkeypatch.setattr(score, "score_job", fake_score_job)

    workers = 4
    t0 = time.time()
    result = score.run(workers=workers, run_post_cleanup=False)
    elapsed = time.time() - t0

    # All 12 jobs scored.
    assert result["score"]["scored"] == 12
    assert result["score"]["errors"] == 0

    # Concurrency proof: 12 jobs * 0.2s sequential = 2.4s. With 4 workers,
    # ideal is 0.6s. Allow generous slack for CI but require <1.5s (well under
    # sequential).
    assert elapsed < 1.5, f"expected concurrent execution, took {elapsed:.2f}s"

    # All results persisted to DB via the bulk UPDATE.
    cur = conn.execute(
        "SELECT url, fit_score, score_reasoning, scored_at FROM jobs ORDER BY url"
    )
    db_rows = cur.fetchall()
    assert len(db_rows) == 12
    for r in db_rows:
        assert r["fit_score"] is not None
        assert r["fit_score"] >= 1
        assert r["score_reasoning"].startswith("kw")
        assert r["scored_at"] is not None


def test_score_run_handles_empty_queue(conn, monkeypatch):
    """No pending_score jobs → no-op, post_cleanup still runs when requested."""
    cleanup_called: list[bool] = []
    monkeypatch.setattr(
        score.cleanup, "post_score", lambda: cleanup_called.append(True) or {"ok": True}
    )

    result = score.run(workers=4, run_post_cleanup=True)

    assert result["score"]["scored"] == 0
    assert cleanup_called == [True]


def test_score_run_isolates_per_job_failures(conn, monkeypatch, tmp_path):
    """One crashing score_job shouldn't tank the whole batch."""
    fake_resume = tmp_path / "resume.txt"
    fake_resume.write_text("fake resume")
    monkeypatch.setattr(score, "RESUME_PATH", fake_resume)
    monkeypatch.setattr(score.cleanup, "post_score", lambda: None)

    conn.executemany(
        "INSERT INTO jobs (url, title, site, full_description) VALUES (?,?,?,?)",
        [
            ("https://example.com/ok", "OK", "test", "desc"),
            ("https://example.com/boom", "Boom", "test", "desc"),
            ("https://example.com/ok2", "OK2", "test", "desc"),
        ],
    )
    conn.commit()

    def flaky_score_job(_resume_text, job):
        if "boom" in job["url"]:
            raise RuntimeError("synthetic failure")
        return {"score": 7, "keywords": "k", "reasoning": "r"}

    monkeypatch.setattr(score, "score_job", flaky_score_job)

    result = score.run(workers=2, run_post_cleanup=False)

    assert result["score"]["scored"] == 3
    assert result["score"]["errors"] == 1

    boom = conn.execute(
        "SELECT fit_score, score_reasoning FROM jobs WHERE url = ?",
        ("https://example.com/boom",),
    ).fetchone()
    assert boom["fit_score"] == 0
    assert "crashed" in boom["score_reasoning"]

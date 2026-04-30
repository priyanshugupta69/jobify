"""HTTP endpoint smoke tests using FastAPI's TestClient."""
from __future__ import annotations

from fastapi.testclient import TestClient

from job_pipeline.main import app


def test_health():
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


def test_stats_returns_keys(conn):
    with TestClient(app) as client:
        r = client.get("/stats")
        assert r.status_code == 200
        body = r.json()
        for key in ("total", "scored", "applied", "tailored"):
            assert key in body


def test_jobs_crud_lifecycle(conn):
    """Insert via SQL, read via GET, update via PATCH, delete via DELETE."""
    conn.execute(
        "INSERT INTO jobs (url, title, site, fit_score) VALUES (?,?,?,?)",
        ("https://test.example/job/1", "Test Engineer", "test", 8),
    )
    conn.commit()

    with TestClient(app) as client:
        r = client.get("/jobs/https://test.example/job/1")
        assert r.status_code == 200
        assert r.json()["title"] == "Test Engineer"

        r = client.patch(
            "/jobs/https://test.example/job/1/application-url",
            json={"application_url": "https://apply.example"},
        )
        assert r.status_code == 200 and r.json()["updated"] is True

        r = client.get("/jobs/https://test.example/job/1")
        assert r.json()["application_url"] == "https://apply.example"

        r = client.delete("/jobs/https://test.example/job/1")
        assert r.status_code == 200 and r.json()["deleted"] == 1

        r = client.get("/jobs/https://test.example/job/1")
        assert r.status_code == 404


def test_jobs_404_for_missing():
    with TestClient(app) as client:
        r = client.get("/jobs/https://nope")
        assert r.status_code == 404

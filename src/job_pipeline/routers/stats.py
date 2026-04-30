"""Aggregate stats endpoints. Wraps applypilot.database.get_stats."""
from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from job_pipeline.db import get_db, get_stats

router = APIRouter(tags=["stats"])


@router.get("/stats")
def stats(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Pipeline-wide counters: total, scored, tailored, applied, etc."""
    return get_stats(conn)

"""Test fixtures: in-memory SQLite that mimics the applypilot schema."""
from __future__ import annotations

import os
import sqlite3
import tempfile
from collections.abc import Iterator

import pytest

# Point applypilot at a temp dir BEFORE importing anything else, so init_db
# writes the test schema there.
_TMP = tempfile.mkdtemp(prefix="jobpipeline-test-")
os.environ["APPLYPILOT_DIR"] = _TMP
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("TELEGRAM_CHAT_ID", "0")
os.environ.setdefault("SCHEDULER_ENABLED", "false")


@pytest.fixture
def conn() -> Iterator[sqlite3.Connection]:
    """Provide a fresh applypilot-schema DB for each test."""
    from applypilot.database import init_db

    db_path = os.path.join(_TMP, "applypilot.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    c = init_db(db_path)
    try:
        yield c
    finally:
        c.close()

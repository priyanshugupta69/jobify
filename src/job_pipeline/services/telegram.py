"""Telegram client. Replaces hardcoded creds in scripts/daily_pipeline.py.

The 5 failing OpenClaw cron jobs all error on a missing chat_id; this
module reads from settings (env / ~/.applypilot/.env) so a single config
fixes them.
"""
from __future__ import annotations

import logging
from pathlib import Path

import httpx

from job_pipeline.settings import settings

log = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"
DEFAULT_TIMEOUT = 20.0


_MARKDOWN_V2_ESCAPE = set("_*[]()~`>#+-=|{}.!")


def escape_markdown(text: str) -> str:
    """Escape MarkdownV2 special characters (matches the helper in daily_pipeline.py)."""
    if not isinstance(text, str):
        return ""
    return "".join("\\" + c if c in _MARKDOWN_V2_ESCAPE else c for c in text)


def _ensure_creds() -> tuple[str, str]:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set "
            "(in env or ~/.applypilot/.env)"
        )
    return settings.telegram_bot_token, settings.telegram_chat_id


def send_message(text: str, parse_mode: str = "MarkdownV2") -> dict:
    token, chat_id = _ensure_creds()
    resp = httpx.post(
        f"{API_BASE}/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
        timeout=DEFAULT_TIMEOUT,
    )
    if resp.status_code != 200:
        log.error("telegram.send_message failed %s: %s", resp.status_code, resp.text[:300])
    resp.raise_for_status()
    return resp.json()


def send_document(path: str | Path, caption: str | None = None) -> dict:
    token, chat_id = _ensure_creds()
    p = Path(path)
    with p.open("rb") as f:
        resp = httpx.post(
            f"{API_BASE}/bot{token}/sendDocument",
            data={"chat_id": chat_id, "caption": caption or ""},
            files={"document": (p.name, f)},
            timeout=DEFAULT_TIMEOUT,
        )
    if resp.status_code != 200:
        log.error("telegram.send_document failed %s: %s", resp.status_code, resp.text[:300])
    resp.raise_for_status()
    return resp.json()

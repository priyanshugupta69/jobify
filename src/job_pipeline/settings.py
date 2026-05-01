"""Application settings loaded from env / ~/.applypilot/.env."""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APPLYPILOT_DIR = Path.home() / ".applypilot"
log = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(APPLYPILOT_DIR / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    llm_model: str = Field(default="gemini-2.5-flash", alias="LLM_MODEL")

    # Telegram (was hardcoded in scripts/daily_pipeline.py)
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")

    # Paths
    applypilot_dir: Path = Field(default=APPLYPILOT_DIR, alias="APPLYPILOT_DIR")

    # FastAPI
    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    cors_origins: list[str] = Field(
        default=["http://localhost:3000"], alias="CORS_ORIGINS"
    )

    # Scheduler
    scheduler_enabled: bool = Field(default=True, alias="SCHEDULER_ENABLED")

    # Auto-apply
    # SAFETY DEFAULT: dry_run=True means Claude fills the form but does NOT click Submit.
    # Flip to false ONLY when you've verified the flow on a real job in dry-run first.
    auto_apply_enabled: bool = Field(default=False, alias="AUTO_APPLY_ENABLED")
    auto_apply_dry_run: bool = Field(default=True, alias="AUTO_APPLY_DRY_RUN")
    auto_apply_model: str = Field(default="sonnet", alias="AUTO_APPLY_MODEL")
    auto_apply_headless: bool = Field(default=True, alias="AUTO_APPLY_HEADLESS")
    # Empty default — the actual binary is resolved at runtime by
    # ``resolve_chrome_path()`` so we don't pin a Playwright revision that
    # silently rots when the playwright pkg version bumps.
    chrome_path: str = Field(default="", alias="CHROME_PATH")

    @property
    def db_path(self) -> Path:
        return self.applypilot_dir / "applypilot.db"


settings = Settings()


def resolve_chrome_path() -> str | None:
    """Locate a usable Chrome/Chromium binary at runtime.

    Order:
      1. ``CHROME_PATH`` env var or ``settings.chrome_path`` — only if the
         file actually exists (so a stale pin from .env auto-falls-through).
      2. Playwright's bundled chromium — whatever revision the currently
         installed ``playwright`` package expects. Survives uv resolves that
         bump the playwright version.
      3. System Chrome via ``shutil.which`` — for boxes with system Chrome.

    Returns the resolved path, or None if nothing is found.
    """
    cand = os.environ.get("CHROME_PATH") or settings.chrome_path
    if cand and Path(cand).exists():
        return cand
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            bundled = p.chromium.executable_path
            if bundled and Path(bundled).exists():
                return bundled
    except Exception as e:
        log.debug("playwright chromium probe failed: %s", e)
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        if (resolved := shutil.which(name)):
            return resolved
    return None

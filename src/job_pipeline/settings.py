"""Application settings loaded from env / ~/.applypilot/.env."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APPLYPILOT_DIR = Path.home() / ".applypilot"


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

    # Scheduler
    scheduler_enabled: bool = Field(default=True, alias="SCHEDULER_ENABLED")

    # Auto-apply
    # SAFETY DEFAULT: dry_run=True means Claude fills the form but does NOT click Submit.
    # Flip to false ONLY when you've verified the flow on a real job in dry-run first.
    auto_apply_enabled: bool = Field(default=False, alias="AUTO_APPLY_ENABLED")
    auto_apply_dry_run: bool = Field(default=True, alias="AUTO_APPLY_DRY_RUN")
    auto_apply_model: str = Field(default="sonnet", alias="AUTO_APPLY_MODEL")
    auto_apply_headless: bool = Field(default=True, alias="AUTO_APPLY_HEADLESS")
    chrome_path: str = Field(
        default="/home/ubuntu/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome",
        alias="CHROME_PATH",
    )

    @property
    def db_path(self) -> Path:
        return self.applypilot_dir / "applypilot.db"


settings = Settings()

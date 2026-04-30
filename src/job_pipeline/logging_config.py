"""Centralized logging setup."""
from __future__ import annotations

import logging
import sys

from job_pipeline.settings import settings


def configure_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-7s %(name)s :: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())
    logging.getLogger("apscheduler").setLevel("INFO")
    logging.getLogger("uvicorn.access").setLevel("WARNING")

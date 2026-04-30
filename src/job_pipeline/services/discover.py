"""Discover + enrich service. Wraps applypilot.pipeline.run_pipeline."""
from __future__ import annotations

import logging
import time

from applypilot.pipeline import run_pipeline

log = logging.getLogger(__name__)


def run(workers: int = 3) -> dict:
    """Run the discover + enrich stages of the applypilot pipeline."""
    log.info("discover.run starting (workers=%d)", workers)
    started = time.time()
    result = run_pipeline(
        stages=["discover", "enrich"],
        workers=workers,
        validation_mode="lenient",
    )
    elapsed = time.time() - started
    log.info("discover.run done in %.1fs: %s", elapsed, result.get("errors", {}))
    return {"elapsed_s": elapsed, **result}

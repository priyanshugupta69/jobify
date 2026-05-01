"""FastAPI app entry point. Lifespan starts/stops the APScheduler."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from job_pipeline.logging_config import configure_logging
from job_pipeline.settings import settings

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    from job_pipeline.patches import apply_patches
    apply_patches()
    log.info("Starting job-pipeline app")

    # Boot-time Chrome self-check — surfaces missing binary at startup
    # instead of mid-cron-run. Run in a thread because resolve_chrome_path
    # uses sync_playwright(), which can't share an event loop with us.
    # Informational only; never raises.
    import asyncio

    from job_pipeline.settings import resolve_chrome_path
    chrome = await asyncio.to_thread(resolve_chrome_path)
    if chrome:
        log.info("Chrome resolved at: %s", chrome)
    else:
        log.warning(
            "No Chrome/Chromium binary found. Run "
            "'uv run playwright install chromium chromium-headless-shell' "
            "or set CHROME_PATH in ~/.applypilot/.env. "
            "Auto-apply / smart_extract / enrich will fail until this is fixed."
        )

    scheduler = None
    if settings.scheduler_enabled:
        from job_pipeline.scheduler import build_scheduler

        scheduler = build_scheduler()
        scheduler.start()
        app.state.scheduler = scheduler
        log.info("Scheduler started with %d jobs", len(scheduler.get_jobs()))
    else:
        app.state.scheduler = None
        log.info("Scheduler disabled (SCHEDULER_ENABLED=false)")

    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)
            log.info("Scheduler stopped")


app = FastAPI(title="job-pipeline", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


# Routers are registered after import to avoid circulars during dev.
from job_pipeline.routers import jobs, stats, pipeline, scheduler as scheduler_router  # noqa: E402

app.include_router(stats.router)
app.include_router(jobs.router)
app.include_router(pipeline.router)
app.include_router(scheduler_router.router)

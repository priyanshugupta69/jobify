# job-pipeline

Consolidated FastAPI app for the daily job-search pipeline (discover → score → tailor → apply).

## Setup

```bash
uv sync
uv run uvicorn job_pipeline.main:app --reload
```

## Structure

- `src/job_pipeline/main.py` — FastAPI app, lifespan starts the scheduler
- `src/job_pipeline/scheduler.py` + `crons.py` — APScheduler with all cron definitions
- `src/job_pipeline/cli.py` — subprocess entry point for heavy scheduled jobs (`python -m job_pipeline.cli <stage>`)
- `src/job_pipeline/routers/` — HTTP endpoints (jobs CRUD, stats, pipeline triggers, scheduler control)
- `src/job_pipeline/services/` — pipeline stage implementations
- `src/job_pipeline/db.py` — wraps `applypilot.database` helpers + custom queries

## Configuration

Reads from `~/.applypilot/.env` and project-level `.env`. Key vars:
- `GEMINI_API_KEY`, `LLM_MODEL`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- `APPLYPILOT_DIR` (defaults to `~/.applypilot`)

## Schedules

Defined in `src/job_pipeline/crons.py`. Ported from `~/.openclaw/cron/jobs.json`. Cron times in UTC.

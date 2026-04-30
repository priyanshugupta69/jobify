# Legacy quarantine

These scripts were copied from `~/.openclaw/workspace/job_pipeline/scripts/`
during the FastAPI consolidation. They were never wired into the daily
cron, the multi-agent flow in WORKFLOW.md, or `daily_pipeline.py` — they
appear to be debugging iterations of a one-off ISS/STOXX Workday auto-apply.

Kept here so the work isn't lost. **Not imported from any service module.**

If/when ISS/STOXX automation is rebuilt, fold the relevant logic into a
proper portal-specific applier in `src/job_pipeline/services/applier/`.

The originals at `~/.openclaw/workspace/job_pipeline/scripts/apply_iss_stoxx*.py`
can be deleted once the new FastAPI service has been verified to cover
everything they ever did (which is none of the cron-driven flow).

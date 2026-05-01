"""Runtime patches against applypilot.

Two patches today:
  - ``employers.yaml`` loader prefers ``APP_DIR/employers.yaml`` over
    applypilot's packaged default (same convention as ``searches.yaml``).
  - When ``VERTEX_SA_KEY`` + ``VERTEX_PROJECT`` + ``VERTEX_LOCATION`` are
    set, route every applypilot LLM call through Vertex AI instead of the
    consumer Gemini API. Cleaner billing, much higher rate limits.
"""
from __future__ import annotations

import logging
import os

import yaml

log = logging.getLogger(__name__)

_PATCHED = False


def _patch_employers_loader() -> None:
    from applypilot import config as ap_config
    from applypilot.discovery import workday

    original = workday.load_employers

    def load_employers_user_first() -> dict:
        user_path = ap_config.APP_DIR / "employers.yaml"
        if user_path.exists():
            try:
                data = yaml.safe_load(user_path.read_text(encoding="utf-8")) or {}
                employers = data.get("employers", {})
                log.info(
                    "load_employers: using %s (%d entries)",
                    user_path, len(employers),
                )
                return employers
            except Exception as e:
                log.warning(
                    "load_employers: user file %s unreadable (%s); "
                    "falling back to package default",
                    user_path, e,
                )
        return original()

    workday.load_employers = load_employers_user_first


def _patch_llm_to_vertex() -> None:
    """If VERTEX_* env vars are set, pre-set applypilot.llm._instance to a
    Vertex-backed client. Subsequent ``get_client()`` calls return it
    instead of probing GEMINI_API_KEY."""
    sa_key = os.environ.get("VERTEX_SA_KEY", "")
    project = os.environ.get("VERTEX_PROJECT", "")
    location = os.environ.get("VERTEX_LOCATION", "")
    if not (sa_key and project and location):
        return

    import applypilot.llm as ap_llm

    if ap_llm._instance is not None:
        # Something already called get_client(); too late to swap cleanly.
        log.warning("LLM client already initialized; Vertex patch skipped.")
        return

    from job_pipeline.vertex_llm import VertexLLMClient

    model = os.environ.get("LLM_MODEL", "gemini-2.5-flash")
    ap_llm._instance = VertexLLMClient(sa_key, project, location, model)
    log.info(
        "LLM provider: Vertex AI (project=%s, location=%s, model=%s)",
        project, location, ap_llm._instance.model,
    )


def apply_patches() -> None:
    """Idempotent — applies all runtime patches against applypilot."""
    global _PATCHED
    if _PATCHED:
        return

    # Load ~/.applypilot/.env into os.environ so downstream patches (and
    # applypilot's own ``_detect_provider``) can read VERTEX_* / GEMINI_API_KEY
    # / etc. without depending on systemd to export them.
    from applypilot.config import load_env
    load_env()

    _patch_employers_loader()
    _patch_llm_to_vertex()

    _PATCHED = True
    log.info("Applied applypilot patches")

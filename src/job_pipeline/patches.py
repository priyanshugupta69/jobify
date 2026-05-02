"""Runtime patches against applypilot.

Patches today:
  - ``employers.yaml`` loader prefers ``APP_DIR/employers.yaml`` over
    applypilot's packaged default (same convention as ``searches.yaml``).
  - ``sites.yaml`` similarly prefers user file.
  - When ``VERTEX_SA_KEY`` + ``VERTEX_PROJECT`` + ``VERTEX_LOCATION`` are
    set, route every applypilot LLM call through Vertex AI instead of the
    consumer Gemini API. Cleaner billing, much higher rate limits.
  - Floor ``LLMClient.chat`` ``max_tokens`` to ``LLM_MIN_MAX_TOKENS``
    (default 8192). Gemini 2.5 Flash/Pro have hidden thinking tokens that
    count against ``max_tokens``; applypilot's hard-coded 2048 leaves so
    little for actual output that JSON gets truncated mid-stream and
    tailor retries hit ``exhausted_retries`` with empty .txt files. See
    src/job_pipeline/services/tailor.py for context.
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


def _patch_sites_loader() -> None:
    """applypilot.discovery.smartextract.load_sites() and config.load_sites_config()
    both read CONFIG_DIR/sites.yaml (packaged), ignoring the user's customizations
    in APP_DIR/sites.yaml. Swap both to prefer the user file with the package
    default as fallback."""
    from applypilot import config as ap_config
    from applypilot.discovery import smartextract

    def _load_sites_yaml() -> dict:
        """Read sites.yaml — user file first, packaged default as fallback."""
        user_path = ap_config.APP_DIR / "sites.yaml"
        if user_path.exists():
            try:
                return yaml.safe_load(user_path.read_text(encoding="utf-8")) or {}
            except Exception as e:
                log.warning(
                    "load_sites: user file %s unreadable (%s); "
                    "falling back to package default",
                    user_path, e,
                )
        pkg_path = ap_config.CONFIG_DIR / "sites.yaml"
        if pkg_path.exists():
            return yaml.safe_load(pkg_path.read_text(encoding="utf-8")) or {}
        return {}

    def load_sites_user_first() -> list[dict]:
        data = _load_sites_yaml()
        sites = data.get("sites", [])
        log.info(
            "load_sites: using %s (%d sites)",
            ap_config.APP_DIR / "sites.yaml" if (ap_config.APP_DIR / "sites.yaml").exists()
            else ap_config.CONFIG_DIR / "sites.yaml",
            len(sites),
        )
        return sites

    def load_sites_config_user_first() -> dict:
        return _load_sites_yaml()

    smartextract.load_sites = load_sites_user_first
    ap_config.load_sites_config = load_sites_config_user_first


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


def _patch_llm_max_tokens_floor() -> None:
    """Floor ``LLMClient.chat``'s ``max_tokens`` to a thinking-aware minimum.

    Why: Gemini 2.5 Flash/Pro emit hidden thinking tokens that count against
    ``max_tokens``. applypilot calls ``chat(..., max_tokens=2048)`` from
    tailor/cover_letter; with a ~3 KB JSON target plus 1–2 KB of thinking,
    2048 tokens isn't enough — output truncates mid-JSON and the retry loop
    can't recover (``extract_json`` always raises ValueError → exhausted).

    The fix doesn't change the call sites; it just enforces a minimum on the
    client itself. Default 8192. Override via ``LLM_MIN_MAX_TOKENS`` env.
    """
    import applypilot.llm as ap_llm

    floor = int(os.environ.get("LLM_MIN_MAX_TOKENS", "8192"))
    original_chat = ap_llm.LLMClient.chat

    # Match the original signature so positional callers still work.
    def chat_with_floor(self, messages, temperature=0.0, max_tokens=4096, **kwargs):
        bumped = max(max_tokens, floor)
        if bumped > max_tokens:
            log.debug(
                "LLMClient.chat: floored max_tokens %s -> %s (model=%s)",
                max_tokens, bumped, getattr(self, "model", "?"),
            )
        return original_chat(
            self, messages, temperature=temperature, max_tokens=bumped, **kwargs
        )

    ap_llm.LLMClient.chat = chat_with_floor
    log.info("Patched LLMClient.chat: max_tokens floor = %d", floor)


def _patch_fabrication_watchlist() -> None:
    """Remove watchlist entries that actually exist in the user's resume.

    Why: ``applypilot/scoring/validator.py`` ships a hardcoded
    ``FABRICATION_WATCHLIST`` (django, vue, ruby, swift, etc.) and substring-
    matches it against the *generated* skills text without consulting the
    user's real resume. For anyone whose resume genuinely lists one of those
    items, the validator hard-fails every tailor attempt with
    "Fabricated skill: 'X'" → ``failed_validation`` → no DB write → bulk
    action sees no_tailored_resume.

    The fix here keeps the safety net for genuinely-unrelated entries (a JS
    dev shouldn't claim Rust) but drops any term the user already has on
    their resume.
    """
    from applypilot import config as ap_config
    from applypilot.scoring import validator as ap_validator

    try:
        resume_text = ap_config.RESUME_PATH.read_text(encoding="utf-8").lower()
    except Exception as e:
        log.warning("fabrication patch: couldn't read resume (%s); skipping", e)
        return

    original = set(ap_validator.FABRICATION_WATCHLIST)
    pruned = {w for w in original if w in resume_text}
    if not pruned:
        log.info("fabrication watchlist: no user-resume overlaps; unchanged")
        return

    ap_validator.FABRICATION_WATCHLIST = original - pruned
    log.info(
        "fabrication watchlist: pruned %d entries already in resume: %s",
        len(pruned), sorted(pruned),
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
    _patch_sites_loader()
    _patch_llm_to_vertex()
    _patch_llm_max_tokens_floor()
    _patch_fabrication_watchlist()

    _PATCHED = True
    log.info("Applied applypilot patches")

"""Runtime patches against applypilot.

applypilot reads ``searches.yaml`` from ``APP_DIR`` (~/.applypilot/) but
reads ``employers.yaml`` from its own packaged config dir, ignoring user
customization. This module patches the loader so user files are
preferred — same convention as ``searches.yaml``.
"""
from __future__ import annotations

import logging

import yaml

log = logging.getLogger(__name__)

_PATCHED = False


def apply_patches() -> None:
    """Idempotent: patches applypilot loaders to prefer APP_DIR files."""
    global _PATCHED
    if _PATCHED:
        return

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
    _PATCHED = True
    log.info("Applied applypilot patches")

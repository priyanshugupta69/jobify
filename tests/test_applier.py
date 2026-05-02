"""Tests for the auto-apply service.

Real submission is never invoked here — we only test gating, validation,
and the dependency checks. Dry-run end-to-end testing requires a live
DB row + Chrome + claude CLI, which lives outside unit tests.
"""
from __future__ import annotations

import importlib

import pytest

import job_pipeline.services.applier as applier_mod


def _set_settings(monkeypatch, **kwargs):
    """Override pydantic settings via env, then reload the module."""
    for k, v in kwargs.items():
        monkeypatch.setenv(k, str(v))
    import job_pipeline.settings as settings_mod
    importlib.reload(settings_mod)
    importlib.reload(applier_mod)


def test_disabled_by_default(monkeypatch):
    """With AUTO_APPLY_ENABLED=false, apply_one raises AutoApplyDisabled.

    Use setenv (not delenv) because pydantic also reads from ~/.applypilot/.env;
    delenv alone lets a local dotfile re-enable it and break the test.
    """
    _set_settings(monkeypatch, AUTO_APPLY_ENABLED="false")
    with pytest.raises(applier_mod.AutoApplyDisabled):
        applier_mod.apply_one("https://anything")


def test_dry_run_is_default_when_enabled(monkeypatch):
    """With AUTO_APPLY_ENABLED=true but no DRY_RUN override, dry_run defaults to true."""
    _set_settings(monkeypatch, AUTO_APPLY_ENABLED="true")
    from job_pipeline.settings import settings
    assert settings.auto_apply_enabled is True
    assert settings.auto_apply_dry_run is True


def test_missing_dependency_raises(monkeypatch):
    """If claude CLI is not on PATH, _ensure_dependencies raises MissingDependency."""
    _set_settings(monkeypatch, AUTO_APPLY_ENABLED="true")
    monkeypatch.setattr("shutil.which", lambda x: None)
    with pytest.raises(applier_mod.MissingDependency):
        applier_mod._ensure_dependencies()


def test_chrome_path_setting_propagated_to_env(monkeypatch, tmp_path):
    """_ensure_chrome_path_exposed sets CHROME_PATH so applypilot's get_chrome_path() finds it.

    The resolver only returns a path that actually exists on disk, so we touch
    a real (empty) file in a tmpdir and point CHROME_PATH at it.
    """
    fake_chrome = tmp_path / "fake-chrome"
    fake_chrome.touch()
    _set_settings(
        monkeypatch,
        AUTO_APPLY_ENABLED="true",
        CHROME_PATH=str(fake_chrome),
    )
    monkeypatch.delenv("CHROME_PATH", raising=False)
    applier_mod._ensure_chrome_path_exposed()
    import os
    assert os.environ.get("CHROME_PATH") == str(fake_chrome)

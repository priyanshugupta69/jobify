"""Verify the employers.yaml monkey-patch picks user file over package."""
from __future__ import annotations

import importlib

import yaml

import job_pipeline.patches as patches_mod


def _reload_applypilot_modules():
    """Reload applypilot.config + workday so APP_DIR re-resolves from env."""
    import applypilot.config
    import applypilot.discovery.workday
    importlib.reload(applypilot.config)
    importlib.reload(applypilot.discovery.workday)


def test_user_employers_yaml_wins(tmp_path, monkeypatch):
    """If APP_DIR/employers.yaml exists, the patch returns its contents."""
    user_dir = tmp_path / "applypilot"
    user_dir.mkdir()
    (user_dir / "employers.yaml").write_text(
        yaml.safe_dump({"employers": {"flipkart": {"name": "Flipkart"}}})
    )
    monkeypatch.setenv("APPLYPILOT_DIR", str(user_dir))

    _reload_applypilot_modules()
    patches_mod._PATCHED = False
    patches_mod.apply_patches()

    from applypilot.discovery.workday import load_employers
    employers = load_employers()
    assert "flipkart" in employers
    assert employers["flipkart"]["name"] == "Flipkart"


def test_falls_back_to_package_default_when_user_file_missing(tmp_path, monkeypatch):
    """If APP_DIR/employers.yaml is absent, the patch defers to the original loader."""
    user_dir = tmp_path / "applypilot"
    user_dir.mkdir()  # exists but no employers.yaml
    monkeypatch.setenv("APPLYPILOT_DIR", str(user_dir))

    _reload_applypilot_modules()
    patches_mod._PATCHED = False
    patches_mod.apply_patches()

    from applypilot.discovery.workday import load_employers
    employers = load_employers()
    # Package version is Canadian-bank-focused; just verify it returns SOMETHING
    # and that flipkart isn't there (proves we're not still using the user file).
    assert isinstance(employers, dict)
    assert len(employers) > 0
    assert "flipkart" not in employers


def test_apply_patches_is_idempotent(tmp_path, monkeypatch):
    """Calling apply_patches() twice should not double-wrap."""
    user_dir = tmp_path / "applypilot"
    user_dir.mkdir()
    (user_dir / "employers.yaml").write_text(
        yaml.safe_dump({"employers": {"x": {"name": "X"}}})
    )
    monkeypatch.setenv("APPLYPILOT_DIR", str(user_dir))

    _reload_applypilot_modules()
    patches_mod._PATCHED = False
    patches_mod.apply_patches()

    from applypilot.discovery import workday
    after_first = workday.load_employers

    patches_mod.apply_patches()  # second call should be a no-op
    assert workday.load_employers is after_first

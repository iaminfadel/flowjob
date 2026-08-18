"""Unit tests for cockpit settings semantics: guardrails, round-trip
comment preservation, atomic writes, and validation routing."""

from pathlib import Path

import pytest
import yaml as pyyaml

from src.tui import settings as settings_mod


@pytest.fixture
def config_file(tmp_path):
    """A copy of the real flowjob.yaml (comments included) in a tmp dir."""
    src = Path("flowjob.yaml")
    assert src.exists(), "flowjob.yaml must exist for this fixture"
    target = tmp_path / "flowjob.yaml"
    target.write_text(src.read_text())
    return str(target)


def test_round_trip_preserves_comments(config_file):
    before = Path(config_file).read_text()
    doc = settings_mod.round_trip_load(config_file)
    assert "providers" in doc["llm"]
    assert "min_wait_minutes" not in doc, "watch section not in repo yaml yet"

    settings_mod.save_settings({"scout": {"max_scrape_per_run": 42}}, config_file)
    after = Path(config_file).read_text()

    for line in before.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            assert stripped in after, f"comment lost: {stripped}"

    doc = settings_mod.round_trip_load(config_file)
    assert doc["scout"]["max_scrape_per_run"] == 42
    assert doc["llm"]["providers"], "providers chain untouched"


def test_save_leaves_other_sections_untouched(config_file):
    doc = settings_mod.round_trip_load(config_file)
    providers_before = [dict(p) for p in doc["llm"]["providers"]]
    writer_before = dict(doc["writer"])

    settings_mod.save_settings({"scout": {"max_scrape_per_run": 7}}, config_file)
    doc = settings_mod.round_trip_load(config_file)
    assert [dict(p) for p in doc["llm"]["providers"]] == providers_before
    assert dict(doc["writer"]) == writer_before


def test_guardrail_violations_reported():
    raw = {
        "scout": {"max_scrape_per_run": 0},
        "applicator": {"max_apps_per_day": 5, "max_apps_per_hour": 10},
        "watch": {"min_wait_minutes": 60, "max_wait_minutes": 30},
        "llm": {"max_retries": -1},
    }
    errors = settings_mod.validate_settings(raw)
    assert any("scout.max_scrape_per_run" in e for e in errors)
    assert any("max_apps_per_hour" in e for e in errors)
    assert any("watch.max_wait_minutes" in e for e in errors)
    assert any("llm.max_retries" in e for e in errors)


def test_clean_config_passes_guardrails():
    raw = {
        "scout": {"max_scrape_per_run": 50},
        "applicator": {"max_apps_per_day": 10, "max_apps_per_hour": 5},
        "watch": {"min_wait_minutes": 30, "max_wait_minutes": 60},
        "llm": {"max_retries": 3},
    }
    assert settings_mod.validate_settings(raw) == []


def test_save_rejects_guardrail_break_and_writes_nothing(config_file):
    raw = {"applicator": {"max_apps_per_day": 5, "max_apps_per_hour": 10}}
    before = Path(config_file).read_text()
    with pytest.raises(settings_mod.SettingsValidationError):
        settings_mod.save_settings(raw, config_file)
    assert Path(config_file).read_text() == before, "file must not change on invalid save"


def test_save_validates_through_pydantic(config_file):
    raw = {"watch": {"min_wait_minutes": 0, "max_wait_minutes": 30}}
    with pytest.raises(Exception):
        settings_mod.save_settings(raw, config_file)


def test_save_uses_atomic_replace(config_file, monkeypatch):
    writes = []

    def fake_replace(src, dst):
        writes.append((str(src), str(dst)))

    monkeypatch.setattr("os.replace", fake_replace)
    settings_mod.save_settings({"scout": {"max_scrape_per_run": 99}}, config_file)
    assert len(writes) == 1
    assert writes[0][1] == config_file
    assert ".tmp" in writes[0][0]


def test_env_overrides_detection(monkeypatch):
    monkeypatch.setenv("FLOWJOB_MODEL", "anthropic/claude-x")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    active = settings_mod.env_overrides_active()
    assert active == {"FLOWJOB_MODEL": "anthropic/claude-x"}

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-secret")
    assert settings_mod.env_overrides_active()["OPENROUTER_API_KEY"] == "set"


def test_editable_sections_cover_watch_and_llm():
    assert "watch" in settings_mod.SECTION_FIELDS
    assert "llm" in settings_mod.SECTION_FIELDS
    assert "providers" not in settings_mod.SECTION_FIELDS["llm"], "providers excluded from form"
    assert "openrouter_api_key" not in settings_mod.SECTION_FIELDS["llm"], "secrets excluded from form"
    assert "require_approval" not in settings_mod.SECTION_FIELDS["applicator"]


def test_settings_pane_fields_match_config_keys(config_file):
    """Every SECTION_FIELDS key must exist in the real config file (watch: absent until saved)."""
    doc = pyyaml.safe_load(Path(config_file).read_text())
    for section, fields in settings_mod.SECTION_FIELDS.items():
        section_data = doc.get(section) or {}
        for key in fields:
            if section == "watch":
                continue  # watch section gets created on first save
            assert key in section_data, f"{section}.{key} missing from flowjob.yaml"
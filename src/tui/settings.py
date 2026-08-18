"""Settings load/save semantics for the cockpit.

ruamel round-trip preserves comments and key order; the providers chain is
never touched. Save validates guardrails, round-trips through FlowJobConfig,
and writes atomically (temp + os.replace + fsync).
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from pydantic import ValidationError
from ruamel.yaml import YAML

from src.config import FlowJobConfig

GUARDRAILS: dict[tuple[str, str], tuple[int | None, int | None]] = {
    ("scout", "max_scrape_per_run"): (1, 500),
    ("analyst", "min_fit_score"): (0, 100),
    ("editor", "min_keyword_coverage"): (0, 100),
    ("writer", "max_writer_rounds"): (1, 10),
    ("grilling", "max_turns_per_gap"): (1, 10),
    ("auditor", "max_attempts"): (1, 10),
    ("applicator", "max_apps_per_day"): (1, 500),
    ("applicator", "max_apps_per_hour"): (1, 24),
    ("llm", "llm_timeout_seconds"): (5, 600),
    ("llm", "max_retries"): (0, 10),
    ("data", "data_retention_days"): (1, 3650),
}

SECTION_FIELDS: dict[str, dict[str, tuple[str, str]]] = {
    "scout": {
        "max_scrape_per_run": ("Max scrape per run", "int"),
        "time_filter": ("Time filter", "str"),
    },
    "analyst": {"model": ("Model", "str"), "min_fit_score": ("Min fit score", "int")},
    "tailor": {"model": ("Model", "str")},
    "editor": {"model": ("Model", "str"), "min_keyword_coverage": ("Min keyword coverage", "int")},
    "critic": {"model": ("Model", "str")},
    "writer": {"model": ("Model", "str"), "max_writer_rounds": ("Max writer rounds", "int")},
    "grilling": {"model": ("Model", "str"), "max_turns_per_gap": ("Max turns per gap", "int")},
    "auditor": {"model": ("Model", "str"), "max_attempts": ("Max attempts", "int")},
    "applicator": {
        "max_apps_per_day": ("Max apps per day", "int"),
        "max_apps_per_hour": ("Max apps per hour", "int"),
        "dry_run": ("Dry run (no apply)", "bool"),
    },
    "llm": {
        "default_model": ("Default model", "str"),
        "llm_timeout_seconds": ("LLM timeout (s)", "int"),
        "max_retries": ("LLM max retries", "int"),
        "openrouter_base_url": ("OpenRouter base URL", "str"),
    },
    "data": {
        "data_retention_days": ("Data retention (days)", "int"),
        "db_path": ("DB path", "str"),
        "output_dir": ("Output dir", "str"),
        "browser_data_dir": ("Browser data dir", "str"),
    },
    "watch": {
        "min_wait_minutes": ("Min wait (min)", "int"),
        "max_wait_minutes": ("Max wait (min)", "int"),
    },
}


class SettingsValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_settings(raw: dict) -> list[str]:
    """Guardrail violations + cross-field checks; empty list means OK."""
    errors: list[str] = []
    for (section, key), (lo, hi) in GUARDRAILS.items():
        value = raw.get(section, {}).get(key)
        if value is None or not isinstance(value, int):
            continue
        if lo is not None and value < lo:
            errors.append(f"{section}.{key} must be >= {lo} (got {value})")
        if hi is not None and value > hi:
            errors.append(f"{section}.{key} must be <= {hi} (got {value})")

    apps_day = raw.get("applicator", {}).get("max_apps_per_day")
    apps_hour = raw.get("applicator", {}).get("max_apps_per_hour")
    if isinstance(apps_day, int) and isinstance(apps_hour, int) and apps_hour > apps_day:
        errors.append(f"applicator.max_apps_per_hour ({apps_hour}) must be <= max_apps_per_day ({apps_day})")

    watch = raw.get("watch", {})
    watch_min = watch.get("min_wait_minutes")
    watch_max = watch.get("max_wait_minutes")
    if isinstance(watch_min, int) and isinstance(watch_max, int) and watch_min >= watch_max:
        errors.append(f"watch.max_wait_minutes ({watch_max}) must be greater than min_wait_minutes ({watch_min})")

    return errors


def round_trip_load(path: str = "flowjob.yaml") -> dict:
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    with open(path, "r") as f:
        return yaml.load(f) or {}


def save_settings(raw: dict, path: str = "flowjob.yaml") -> None:
    """Validate then write atomically; raises SettingsValidationError / ValidationError."""
    errors = validate_settings(raw)
    if errors:
        raise SettingsValidationError(errors)

    doc = round_trip_load(path)
    for section, values in raw.items():
        if section not in doc or doc[section] is None:
            doc[section] = {}
        for key, value in values.items():
            doc[section][key] = value

    config = FlowJobConfig(**dict(doc))

    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    target = Path(path)
    tmp_path = target.with_name(f".{target.name}.tmp")
    try:
        with open(tmp_path, "w") as f:
            yaml.dump(doc, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, target)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


def env_overrides_active() -> dict[str, str]:
    """Env overrides that shadow file values at load time."""
    active: dict[str, str] = {}
    if os.environ.get("FLOWJOB_MODEL"):
        active["FLOWJOB_MODEL"] = os.environ["FLOWJOB_MODEL"]
    if os.environ.get("OPENROUTER_API_KEY"):
        active["OPENROUTER_API_KEY"] = "set"
    return active


def run_full_validation(path: str = "flowjob.yaml") -> list[str]:
    """The 'Re-validate' action: config + master resume + DB init."""
    from src.config import load_config
    from scripts.validate_resume import validate_resume
    from src.db.store import init_db

    errors: list[str] = []
    try:
        cfg = load_config(path)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"config: {exc}")
        return errors
    if not validate_resume("master_resume.md"):
        errors.append("master_resume.md failed validation")
    try:
        init_db(cfg.data.db_path)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"db: {exc}")
    return errors
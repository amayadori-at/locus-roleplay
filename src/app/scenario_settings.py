from __future__ import annotations

import json
from typing import Any

from app.ids import is_locus_id
from app.vault import Vault, VaultError, VaultFileError

PROMPT_GRAPH_MODES = frozenset({"common", "per_start"})
DEFAULT_PROMPT_GRAPH_MODE = "common"


class ScenarioSettingsError(VaultError):
    """Raised when scenario settings are invalid or unreadable."""


def read_scenario_settings(vault: Vault, scenario_id: str) -> dict[str, Any]:
    """Read scenario_settings.json. Returns defaults if the file does not exist."""
    _validate_scenario_id(scenario_id)
    settings_path = _settings_path(scenario_id)
    settings_file = vault.resolve(settings_path)
    if not settings_file.exists():
        return _defaults()
    try:
        raw = vault.load_json(settings_path)
    except VaultFileError as exc:
        raise ScenarioSettingsError(f"scenario_settings.json is unreadable: {settings_path}") from exc
    return _validate(raw, settings_path)


def write_scenario_settings(vault: Vault, scenario_id: str, settings: dict[str, Any]) -> dict[str, Any]:
    """Validate and write scenario_settings.json. Returns the saved settings."""
    _validate_scenario_id(scenario_id)
    validated = _validate(settings, _settings_path(scenario_id))
    path = vault.resolve(_settings_path(scenario_id))
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(validated, ensure_ascii=False, indent=2) + "\n"
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        temp_path.write_text(raw, encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return validated


def _validate(raw: object, settings_path: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ScenarioSettingsError(f"scenario_settings.json root must be a JSON object: {settings_path}")
    mode = raw.get("prompt_graph_mode", DEFAULT_PROMPT_GRAPH_MODE)
    if mode not in PROMPT_GRAPH_MODES:
        raise ScenarioSettingsError(
            f"scenario_settings.json prompt_graph_mode must be one of {sorted(PROMPT_GRAPH_MODES)}: {settings_path}"
        )
    return {"prompt_graph_mode": mode}


def _defaults() -> dict[str, Any]:
    return {"prompt_graph_mode": DEFAULT_PROMPT_GRAPH_MODE}


def _settings_path(scenario_id: str) -> str:
    return f"rp/scenarios/{scenario_id}/scenario_settings.json"


def _validate_scenario_id(scenario_id: str) -> None:
    if not is_locus_id(scenario_id):
        raise ScenarioSettingsError(f"Invalid scenario id: {scenario_id}")

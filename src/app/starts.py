from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

import yaml

from app.ids import is_locus_id
from app.loaders import list_startings, load_starting
from app.vault import Vault, VaultError


class StartError(VaultError):
    """Raised when a start is missing, invalid, or unsafe."""


@dataclass(frozen=True)
class StartManifest:
    starting_id: str
    name: str
    description: str
    lore_include: list[str]
    lore_exclude: list[str]
    initial_state_path: str | None


@dataclass(frozen=True)
class StartInfo:
    id: str
    name: str
    body: str
    has_manifest: bool


def list_starts(vault: Vault, scenario_id: str) -> list[StartInfo]:
    """List all starts. A start is any startings/{id}.md file."""
    _validate_scenario_id(scenario_id)
    ids = list_startings(vault, scenario_id)
    result = []
    for starting_id in ids:
        starting = load_starting(vault, scenario_id, starting_id)
        has_manifest = vault.resolve(
            f"rp/scenarios/{scenario_id}/startings/{starting_id}/manifest.yaml"
        ).is_file()
        result.append(StartInfo(id=starting_id, name=starting.name, body=starting.body, has_manifest=has_manifest))
    return result


def read_start_manifest(vault: Vault, scenario_id: str, starting_id: str) -> StartManifest:
    """Read startings/{starting_id}/manifest.yaml.

    If the manifest file is absent, returns a default manifest with no Lore filtering.
    Raises StartError if the start .md itself does not exist.
    """
    _validate_ids(scenario_id, starting_id)
    desc_path = vault.resolve(f"rp/scenarios/{scenario_id}/startings/{starting_id}.md")
    if not desc_path.exists():
        raise StartError(f"Start not found: {starting_id}")

    manifest_path = f"rp/scenarios/{scenario_id}/startings/{starting_id}/manifest.yaml"
    manifest_file = vault.resolve(manifest_path)

    if not manifest_file.exists():
        starting = load_starting(vault, scenario_id, starting_id)
        return StartManifest(
            starting_id=starting_id,
            name=starting.name,
            description="",
            lore_include=[],
            lore_exclude=[],
            initial_state_path=None,
        )

    try:
        raw_text = manifest_file.read_text(encoding="utf-8")
        raw = yaml.safe_load(raw_text)
    except Exception as exc:
        raise StartError(f"Failed to read start manifest: {manifest_path}") from exc

    if not isinstance(raw, dict):
        raise StartError(f"Start manifest root must be a YAML object: {manifest_path}")

    lore_include = _parse_id_list(raw, "lore_include", manifest_path)
    lore_exclude = _parse_id_list(raw, "lore_exclude", manifest_path)
    initial_state_path = _parse_initial_state_path(raw, manifest_path)

    name = raw.get("name", "")
    if not isinstance(name, str) or not name.strip():
        starting = load_starting(vault, scenario_id, starting_id)
        name = starting.name

    description = raw.get("description", "")
    if not isinstance(description, str):
        description = ""

    return StartManifest(
        starting_id=starting_id,
        name=name,
        description=description,
        lore_include=lore_include,
        lore_exclude=lore_exclude,
        initial_state_path=initial_state_path,
    )


def filter_lore_ids(all_lore_ids: list[str], manifest: StartManifest) -> list[str]:
    """Apply lore_include and lore_exclude to filter a list of lore IDs.

    - lore_exclude removes IDs from the list.
    - lore_include ensures those IDs are present (adds if missing).
    - Empty lists mean no filtering on that side.
    - Mod applies after start: callers should apply mod add/exclude after this call.
    """
    ids = list(all_lore_ids)
    if manifest.lore_exclude:
        exclude_set = set(manifest.lore_exclude)
        ids = [lore_id for lore_id in ids if lore_id not in exclude_set]
    if manifest.lore_include:
        existing = set(ids)
        for include_id in manifest.lore_include:
            if include_id not in existing:
                ids.append(include_id)
    return ids


def resolve_initial_state_path(scenario_id: str, starting_id: str, manifest: StartManifest) -> str:
    """Return the vault-relative path for the initial state file of a start.

    Falls back to the scenario-level initial state if manifest has no override.
    """
    if manifest.initial_state_path:
        return f"rp/scenarios/{scenario_id}/startings/{starting_id}/{manifest.initial_state_path}"
    return f"rp/scenarios/{scenario_id}/state/current.json"


def _parse_id_list(raw: dict[str, Any], key: str, manifest_path: str) -> list[str]:
    value = raw.get(key) or []
    if not isinstance(value, list):
        raise StartError(f"Start manifest '{key}' must be a list: {manifest_path}")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise StartError(f"Start manifest '{key}' items must be non-empty strings: {manifest_path}")
        if not is_locus_id(item):
            raise StartError(f"Start manifest '{key}' contains invalid id '{item}': {manifest_path}")
        result.append(item)
    return result


def _parse_initial_state_path(raw: dict[str, Any], manifest_path: str) -> str | None:
    value = raw.get("initial_state")
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise StartError(f"Start manifest 'initial_state' must be a non-empty string: {manifest_path}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts) or len(path.parts) != 1:
        raise StartError(f"Start manifest 'initial_state' path is unsafe: {value}")
    if not value.endswith(".json"):
        raise StartError(f"Start manifest 'initial_state' must be a .json filename: {value}")
    return value


def write_start_manifest(
    vault: Vault,
    scenario_id: str,
    starting_id: str,
    name: str,
    description: str,
    lore_include: list[str],
    lore_exclude: list[str],
    initial_state_path: str | None,
) -> StartManifest:
    """Write startings/{starting_id}/manifest.yaml.

    Validates all IDs and the initial_state filename before writing.
    Raises StartError if the start .md does not exist or inputs are invalid.
    """
    _validate_ids(scenario_id, starting_id)
    desc_path = vault.resolve(f"rp/scenarios/{scenario_id}/startings/{starting_id}.md")
    if not desc_path.exists():
        raise StartError(f"Start not found: {starting_id}")

    if not isinstance(name, str) or not name.strip():
        raise StartError("manifest name must not be empty")
    if not isinstance(description, str):
        raise StartError("manifest description must be a string")

    validated_include: list[str] = []
    for item in lore_include:
        if not isinstance(item, str) or not item.strip():
            raise StartError("lore_include items must be non-empty strings")
        if not is_locus_id(item):
            raise StartError(f"lore_include contains invalid id: {item!r}")
        validated_include.append(item)

    validated_exclude: list[str] = []
    for item in lore_exclude:
        if not isinstance(item, str) or not item.strip():
            raise StartError("lore_exclude items must be non-empty strings")
        if not is_locus_id(item):
            raise StartError(f"lore_exclude contains invalid id: {item!r}")
        validated_exclude.append(item)

    validated_initial: str | None = None
    if initial_state_path is not None:
        path = PurePosixPath(initial_state_path)
        if (
            not initial_state_path
            or path.is_absolute()
            or any(part in ("", ".", "..") for part in path.parts)
            or len(path.parts) != 1
        ):
            raise StartError(f"initial_state path is unsafe: {initial_state_path}")
        if not initial_state_path.endswith(".json"):
            raise StartError("initial_state must be a .json filename")
        validated_initial = initial_state_path

    manifest_dir = vault.resolve(f"rp/scenarios/{scenario_id}/startings/{starting_id}")
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / "manifest.yaml"

    data: dict[str, Any] = {
        "id": starting_id,
        "name": name.strip(),
    }
    if description.strip():
        data["description"] = description.strip()
    if validated_include:
        data["lore_include"] = validated_include
    if validated_exclude:
        data["lore_exclude"] = validated_exclude
    if validated_initial:
        data["initial_state"] = validated_initial

    manifest_path.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    return StartManifest(
        starting_id=starting_id,
        name=name.strip(),
        description=description.strip(),
        lore_include=validated_include,
        lore_exclude=validated_exclude,
        initial_state_path=validated_initial,
    )


def create_start(
    vault: Vault,
    scenario_id: str,
    starting_id: str,
    name: str,
    body: str = "",
) -> StartInfo:
    """Create a new start: writes startings/{starting_id}.md.

    Raises StartError if the start already exists.
    """
    _validate_ids(scenario_id, starting_id)
    if not name.strip():
        raise StartError("Start name must not be empty")
    desc_path = vault.resolve(f"rp/scenarios/{scenario_id}/startings/{starting_id}.md")
    if desc_path.exists():
        raise StartError(f"Start already exists: {starting_id}")
    desc_path.parent.mkdir(parents=True, exist_ok=True)
    content = f"---\ntype: starting\nid: {starting_id}\nname: {name}\n---\n\n{body}"
    desc_path.write_text(content, encoding="utf-8")
    return StartInfo(id=starting_id, name=name, body=body, has_manifest=False)


def delete_start(vault: Vault, scenario_id: str, starting_id: str) -> None:
    """Delete startings/{starting_id}.md and startings/{starting_id}/ directory.

    Raises StartError if the start does not exist.
    """
    _validate_ids(scenario_id, starting_id)
    desc_path = vault.resolve(f"rp/scenarios/{scenario_id}/startings/{starting_id}.md")
    if not desc_path.exists():
        raise StartError(f"Start not found: {starting_id}")
    desc_path.unlink()
    subdir = vault.resolve(f"rp/scenarios/{scenario_id}/startings/{starting_id}")
    if subdir.exists() and subdir.is_dir():
        shutil.rmtree(subdir)


def _validate_scenario_id(scenario_id: str) -> None:
    if not is_locus_id(scenario_id):
        raise StartError(f"Invalid scenario id: {scenario_id}")


def _validate_ids(scenario_id: str, starting_id: str) -> None:
    _validate_scenario_id(scenario_id)
    if not is_locus_id(starting_id):
        raise StartError(f"Invalid start id: {starting_id}")

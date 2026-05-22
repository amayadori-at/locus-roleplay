from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.ids import is_locus_id
from app.vault import MarkdownDocument, Vault, VaultError, VaultFileError


PROFILE_REQUIRED_FIELDS = ("id", "kind", "api_type", "api_key_env", "model", "context_size")
SECRET_PROFILE_FIELDS = {"api_key", "key", "secret", "token", "authorization"}


class LoaderError(VaultError):
    """Raised when a domain object cannot be loaded from the Vault."""


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    metadata: dict[str, Any]
    body: str
    system_prompt: str
    current_state: Any
    gm_system: str = ""
    narration_policy: str = ""
    image_policy: str = ""


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    metadata: dict[str, Any]
    body: str


@dataclass(frozen=True)
class ModelProfile:
    id: str
    kind: str
    data: dict[str, Any]


@dataclass(frozen=True)
class StartingMessage:
    id: str
    name: str
    metadata: dict[str, Any]
    body: str


def list_scenarios(vault: Vault) -> list[str]:
    base = vault.resolve("rp/scenarios")
    if not base.exists():
        return []
    if not base.is_dir():
        raise LoaderError("rp/scenarios is not a directory")

    scenario_ids: list[str] = []
    for child in sorted(base.iterdir(), key=lambda item: item.name):
        if child.is_dir() and is_locus_id(child.name) and (child / "scenario.md").is_file():
            scenario_ids.append(child.name)
    return scenario_ids


def load_scenario(vault: Vault, scenario_id: str) -> Scenario:
    _validate_id(scenario_id, "scenario")
    base = f"rp/scenarios/{scenario_id}"
    scenario_doc = _load_required_markdown(vault, f"{base}/scenario.md")
    system_prompt = _load_required_text(vault, f"{base}/system_prompt.md")
    current_state = vault.load_json(f"{base}/state/current.json")
    gm_system = _load_optional_text(vault, f"{base}/gm/gm_system.md")
    narration_policy = _load_optional_text(vault, f"{base}/gm/narration_policy.md")
    image_policy = _load_optional_text(vault, f"{base}/gm/image_policy.md")

    metadata = dict(scenario_doc.frontmatter)
    _require_markdown_type(metadata, "scenario", f"{base}/scenario.md")
    _require_matching_id(metadata, scenario_id, f"{base}/scenario.md")
    name = _require_string(metadata, "name", f"{base}/scenario.md")

    return Scenario(
        id=scenario_id,
        name=name,
        metadata=metadata,
        body=scenario_doc.body,
        system_prompt=system_prompt,
        current_state=current_state,
        gm_system=gm_system,
        narration_policy=narration_policy,
        image_policy=image_policy,
    )


def list_startings(vault: Vault, scenario_id: str) -> list[str]:
    _validate_id(scenario_id, "scenario")
    base = vault.resolve(f"rp/scenarios/{scenario_id}/startings")
    if not base.exists():
        return []
    if not base.is_dir():
        raise LoaderError(f"startings path is not a directory: {scenario_id}")

    starting_ids: list[str] = []
    for child in sorted(base.iterdir(), key=lambda item: item.name):
        if child.is_file() and child.suffix == ".md" and is_locus_id(child.stem):
            starting_ids.append(child.stem)
    return starting_ids


def load_starting(vault: Vault, scenario_id: str, starting_id: str) -> StartingMessage:
    _validate_id(scenario_id, "scenario")
    _validate_id(starting_id, "start")
    path = f"rp/scenarios/{scenario_id}/startings/{starting_id}.md"
    document = _load_required_markdown(vault, path)
    metadata = dict(document.frontmatter)
    _require_markdown_type(metadata, "starting", path)
    _require_matching_id(metadata, starting_id, path)
    name = _require_string(metadata, "name", path)
    return StartingMessage(id=starting_id, name=name, metadata=metadata, body=document.body.strip())


def list_personas(vault: Vault) -> list[str]:
    base = vault.resolve("rp/personas")
    if not base.exists():
        return []
    if not base.is_dir():
        raise LoaderError("rp/personas is not a directory")

    persona_ids: list[str] = []
    for child in sorted(base.iterdir(), key=lambda item: item.name):
        if child.is_file() and child.suffix == ".md" and is_locus_id(child.stem):
            persona_ids.append(child.stem)
    return persona_ids


def load_persona(vault: Vault, persona_id: str) -> Persona:
    _validate_id(persona_id, "persona")
    path = f"rp/personas/{persona_id}.md"
    document = _load_required_markdown(vault, path)
    metadata = dict(document.frontmatter)
    _require_markdown_type(metadata, "persona", path)
    _require_matching_id(metadata, persona_id, path)
    name = _require_string(metadata, "name", path)

    return Persona(id=persona_id, name=name, metadata=metadata, body=document.body)


def list_profiles(vault: Vault) -> list[str]:
    base = vault.resolve("rp/profiles")
    if not base.exists():
        return []
    if not base.is_dir():
        raise LoaderError("rp/profiles is not a directory")

    profile_ids: list[str] = []
    for child in sorted(base.iterdir(), key=lambda item: item.name):
        if child.is_file() and child.suffix == ".json" and is_locus_id(child.stem):
            profile_ids.append(child.stem)
    return profile_ids


def load_profile(vault: Vault, profile_id: str) -> ModelProfile:
    _validate_id(profile_id, "profile")
    path = f"rp/profiles/{profile_id}.json"
    raw = vault.load_json(path)
    if not isinstance(raw, dict):
        raise LoaderError(f"Profile must be a JSON object: {path}")

    data = dict(raw)
    _validate_profile(data, profile_id, path)
    return ModelProfile(id=profile_id, kind=data["kind"], data=data)


def _validate_profile(data: dict[str, Any], profile_id: str, path: str) -> None:
    lower_keys = {str(key).lower() for key in data.keys()}
    suspicious = sorted(lower_keys & SECRET_PROFILE_FIELDS)
    if suspicious:
        raise LoaderError(f"Profile contains forbidden secret field(s) in {path}: {', '.join(suspicious)}")

    for field in PROFILE_REQUIRED_FIELDS:
        if field not in data:
            raise LoaderError(f"Profile missing required field '{field}': {path}")

    _require_matching_id(data, profile_id, path)
    _require_string(data, "kind", path)
    api_type = _require_string(data, "api_type", path)
    if api_type != "openai_compatible":
        raise LoaderError(f"Unsupported profile api_type '{api_type}': {path}")
    if "endpoint" not in data and "endpoint_env" not in data:
        raise LoaderError(f"Profile must define 'endpoint' or 'endpoint_env': {path}")
    if "endpoint" in data:
        _require_string(data, "endpoint", path)
    if "endpoint_env" in data:
        _require_string(data, "endpoint_env", path)
    _require_string(data, "api_key_env", path)
    _require_string(data, "model", path)
    _require_number(data, "context_size", path)

    for optional_number in ("temperature", "top_p", "top_k", "max_tokens", "frequency_penalty", "presence_penalty", "repetition_penalty", "timeout_seconds", "retry_count"):
        if optional_number in data:
            _require_number(data, optional_number, path)
    if "reasoning_effort" in data and not isinstance(data["reasoning_effort"], str):
        raise LoaderError(f"Profile field 'reasoning_effort' must be a string: {path}")
    if "stop" in data and not isinstance(data["stop"], list):
        raise LoaderError(f"Profile field 'stop' must be an array: {path}")
    if "stop" in data and not all(isinstance(item, str) for item in data["stop"]):
        raise LoaderError(f"Profile field 'stop' must contain only strings: {path}")


def _load_required_text(vault: Vault, relative_path: str) -> str:
    try:
        return vault.read_text(relative_path)
    except VaultFileError as exc:
        raise LoaderError(f"Required file is missing or unreadable: {relative_path}") from exc


def _load_optional_text(vault: Vault, relative_path: str) -> str:
    try:
        return vault.read_text(relative_path)
    except VaultFileError:
        return ""


def _load_required_markdown(vault: Vault, relative_path: str) -> MarkdownDocument:
    try:
        return vault.load_markdown(relative_path)
    except VaultFileError as exc:
        raise LoaderError(f"Required Markdown file is missing or invalid: {relative_path}") from exc


def _validate_id(value: str, kind: str) -> None:
    if not is_locus_id(value):
        raise LoaderError(f"Invalid {kind} id: {value}")


def _require_markdown_type(metadata: dict[str, Any], expected: str, path: str) -> None:
    actual = _require_string(metadata, "type", path)
    if actual != expected:
        raise LoaderError(f"Expected type '{expected}' in {path}, got '{actual}'")


def _require_matching_id(metadata: dict[str, Any], expected: str, path: str) -> None:
    actual = _require_string(metadata, "id", path)
    if actual != expected:
        raise LoaderError(f"Expected id '{expected}' in {path}, got '{actual}'")


def _require_string(data: dict[str, Any], field: str, path: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise LoaderError(f"Field '{field}' must be a non-empty string: {path}")
    return value


def _require_number(data: dict[str, Any], field: str, path: str) -> int | float:
    value = data.get(field)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise LoaderError(f"Field '{field}' must be a number: {path}")
    return value

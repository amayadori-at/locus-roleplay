from __future__ import annotations

import json
from pathlib import PurePosixPath
from typing import Any

from app.ids import is_locus_id
from app.vault import VaultError


class ApiBadRequest(VaultError):
    pass


def validate_id(value: str, kind: str) -> str:
    if not is_locus_id(value):
        raise VaultError(f"Invalid {kind} id: {value}")
    return value


def validate_scenario_source_path(value: str) -> str:
    if not value or not isinstance(value, str):
        raise ApiBadRequest("source path must be a non-empty string")
    if "\\" in value:
        raise ApiBadRequest("source path must not contain backslashes")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ApiBadRequest("source path contains an unsafe segment")
    normalized = path.as_posix()
    if not is_allowed_scenario_source_path(normalized):
        raise ApiBadRequest("source path is not editable in the scenario viewer")
    return normalized


def validate_new_scenario_source_path(value: str) -> str:
    safe_path = validate_scenario_source_path(value)
    parts = PurePosixPath(safe_path).parts
    if len(parts) != 2 or parts[0] not in {"gm", "characters", "lore", "startings"}:
        raise ApiBadRequest("new source files can only be created under gm, characters, lore, or startings")
    return safe_path


def validate_deletable_scenario_source_path(value: str) -> str:
    safe_path = validate_scenario_source_path(value)
    parts = PurePosixPath(safe_path).parts
    if len(parts) != 2 or parts[0] not in {"gm", "characters", "lore", "startings"}:
        raise ApiBadRequest("only gm, characters, lore, or startings source files can be deleted")
    return safe_path


def is_allowed_scenario_source_path(value: str) -> bool:
    path = PurePosixPath(value)
    parts = path.parts
    if len(parts) == 1:
        return parts[0] in {"scenario.md", "system_prompt.md"}
    if len(parts) == 2 and parts[1].endswith(".md"):
        return parts[0] in {"gm", "characters", "lore", "startings"} and is_locus_id(parts[1].removesuffix(".md"))
    if len(parts) == 3 and parts[0] == "memory" and parts[2].endswith(".md"):
        return parts[1] in {"session_summaries", "extracted_facts", "unresolved_threads"} and is_locus_id(
            parts[2].removesuffix(".md")
        )
    return False


def require_id(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str):
        raise ApiBadRequest(f"Missing required field: {field}")
    return validate_id(value, field)


def require_string_payload(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ApiBadRequest(f"Missing required field: {field}")
    return value.strip()


def optional_id(payload: dict[str, Any], field: str) -> str | None:
    value = payload.get(field)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ApiBadRequest(f"Field must be a string: {field}")
    return validate_id(value, field)


def require_metadata_id(metadata: dict[str, Any], field: str) -> str:
    value = metadata.get(field)
    if not isinstance(value, str):
        raise ApiBadRequest(f"Parent session metadata is missing required field: {field}")
    return validate_id(value, field)


def optional_metadata_id(metadata: dict[str, Any], field: str) -> str | None:
    value = metadata.get(field)
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise ApiBadRequest(f"Parent session metadata field must be a string: {field}")
    return validate_id(value, field)


def optional_query_id(query: dict[str, list[str]], field: str) -> str | None:
    value = query.get(field, [""])[0]
    if not value:
        return None
    return validate_id(value, field)


def query_string(query: dict[str, list[str]], field: str, *, required: bool = True) -> str:
    value = query.get(field, [""])[0]
    if required and not value.strip():
        raise ApiBadRequest(f"Missing required query parameter: {field}")
    return value


def optional_positive_int_query(query: dict[str, list[str]], field: str) -> int | None:
    value = query.get(field, [""])[0]
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ApiBadRequest(f"{field} must be a positive integer") from exc
    if parsed <= 0:
        raise ApiBadRequest(f"{field} must be a positive integer")
    return parsed


def optional_non_negative_int_query(query: dict[str, list[str]], field: str) -> int | None:
    value = query.get(field, [""])[0]
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ApiBadRequest(f"{field} must be a non-negative integer") from exc
    if parsed < 0:
        raise ApiBadRequest(f"{field} must be a non-negative integer")
    return parsed


def decode_json_body(body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(body.decode("utf-8") if body else "{}")
    except json.JSONDecodeError as exc:
        raise ApiBadRequest("Request body must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ApiBadRequest("Request body must be a JSON object")
    return payload

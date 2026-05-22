from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.ids import is_locus_id
from app.messages import CHAT_ROLES
from app.vault import Vault, VaultError


class StateSessionError(VaultError):
    """Raised when state or session persistence fails."""


class StatePatchError(StateSessionError):
    """Raised when a state patch output is malformed."""


MAX_STATE_PATCH_BYTES = 64 * 1024
DANGEROUS_STATE_KEYS = {"__proto__", "prototype", "constructor"}


@dataclass(frozen=True)
class SessionMetadata:
    session_id: str
    scenario_id: str
    persona_id: str
    rp_profile_id: str
    summary_profile_id: str | None = None
    turn_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None
    starting_id: str | None = None

    def to_json(self) -> dict[str, Any]:
        now = _now_iso()
        data: dict[str, Any] = {
            "session_id": self.session_id,
            "scenario_id": self.scenario_id,
            "persona_id": self.persona_id,
            "rp_profile_id": self.rp_profile_id,
            "summary_profile_id": self.summary_profile_id,
            "turn_count": self.turn_count,
            "created_at": self.created_at or now,
            "updated_at": self.updated_at or now,
        }
        if self.starting_id is not None:
            data["starting_id"] = self.starting_id
        return data


def read_current_state(vault: Vault, scenario_id: str) -> dict[str, Any]:
    return read_initial_state(vault, scenario_id)


def read_initial_state(vault: Vault, scenario_id: str) -> dict[str, Any]:
    _validate_id(scenario_id, "scenario")
    state = vault.load_json(_initial_state_path(scenario_id))
    if not isinstance(state, dict):
        raise StateSessionError(f"Initial state must be a JSON object: {_initial_state_path(scenario_id)}")
    return state


def write_current_state(vault: Vault, scenario_id: str, state: dict[str, Any]) -> None:
    write_initial_state(vault, scenario_id, state)


def write_initial_state(vault: Vault, scenario_id: str, state: dict[str, Any]) -> None:
    _validate_id(scenario_id, "scenario")
    if not isinstance(state, dict):
        raise StateSessionError("Initial state must be a JSON object")
    _write_json_file(vault, _initial_state_path(scenario_id), state)


def read_session_state(vault: Vault, scenario_id: str, session_id: str) -> dict[str, Any]:
    _validate_id(scenario_id, "scenario")
    _validate_id(session_id, "session")
    session_state_path = vault.resolve(_session_state_path(scenario_id, session_id))
    if session_state_path.exists():
        state = vault.load_json(_session_state_path(scenario_id, session_id))
        if not isinstance(state, dict):
            raise StateSessionError(f"Session state must be a JSON object: {_session_state_path(scenario_id, session_id)}")
        return state
    print(
        f"[state_session] session state not found for session={session_id}, scenario={scenario_id}; "
        "falling back to initial state (lazy migration)",
        file=sys.stderr,
    )
    return read_initial_state(vault, scenario_id)


def write_session_state(vault: Vault, scenario_id: str, session_id: str, state: dict[str, Any]) -> None:
    _validate_id(scenario_id, "scenario")
    _validate_id(session_id, "session")
    if not isinstance(state, dict):
        raise StateSessionError("Session state must be a JSON object")
    _write_json_file(vault, _session_state_path(scenario_id, session_id), state)


def initialize_session_state(
    vault: Vault,
    scenario_id: str,
    session_id: str,
    source_vault_path: str | None = None,
) -> dict[str, Any]:
    if source_vault_path is not None:
        source_file = vault.resolve(source_vault_path)
        if not source_file.exists():
            raise StateSessionError(f"Start initial state file not found: {source_vault_path}")
        raw = vault.load_json(source_vault_path)
        if not isinstance(raw, dict):
            raise StateSessionError(f"Start initial state must be a JSON object: {source_vault_path}")
        state = raw
    else:
        state = read_initial_state(vault, scenario_id)
    write_session_state(vault, scenario_id, session_id, state)
    write_session_state_snapshot(vault, scenario_id, session_id, 0, state)
    return state


def copy_session_state(
    vault: Vault,
    scenario_id: str,
    source_session_id: str,
    target_session_id: str,
) -> dict[str, Any]:
    state = read_session_state(vault, scenario_id, source_session_id)
    write_session_state(vault, scenario_id, target_session_id, state)
    return state


def read_session_state_snapshot(vault: Vault, scenario_id: str, session_id: str, turn: int) -> dict[str, Any]:
    _validate_turn(turn)
    state = vault.load_json(_session_state_snapshot_path(scenario_id, session_id, turn))
    if not isinstance(state, dict):
        raise StateSessionError(
            f"Session state snapshot must be a JSON object: {_session_state_snapshot_path(scenario_id, session_id, turn)}"
        )
    return state


def write_session_state_snapshot(
    vault: Vault,
    scenario_id: str,
    session_id: str,
    turn: int,
    state: dict[str, Any],
) -> None:
    _validate_id(scenario_id, "scenario")
    _validate_id(session_id, "session")
    _validate_turn(turn)
    if not isinstance(state, dict):
        raise StateSessionError("Session state snapshot must be a JSON object")
    _write_json_file(vault, _session_state_snapshot_path(scenario_id, session_id, turn), state)


def read_session_state_for_turn(vault: Vault, scenario_id: str, session_id: str, turn: int) -> dict[str, Any]:
    _validate_turn(turn)
    snapshot_path = vault.resolve(_session_state_snapshot_path(scenario_id, session_id, turn))
    if snapshot_path.exists():
        return read_session_state_snapshot(vault, scenario_id, session_id, turn)
    return read_session_state(vault, scenario_id, session_id)


def copy_session_state_for_turn(
    vault: Vault,
    scenario_id: str,
    source_session_id: str,
    target_session_id: str,
    turn: int,
) -> dict[str, Any]:
    state = read_session_state_for_turn(vault, scenario_id, source_session_id, turn)
    write_session_state(vault, scenario_id, target_session_id, state)
    write_session_state_snapshot(vault, scenario_id, target_session_id, turn, state)
    return state


def apply_state_patch_output(vault: Vault, scenario_id: str, patch_output: str | dict[str, Any]) -> dict[str, Any]:
    current_state = read_current_state(vault, scenario_id)
    patch = parse_patch_output(patch_output)
    validate_state_patch(current_state, patch)
    next_state = deep_merge(current_state, patch)
    write_current_state(vault, scenario_id, next_state)
    return next_state


def apply_session_state_patch_output(
    vault: Vault,
    scenario_id: str,
    session_id: str,
    patch_output: str | dict[str, Any],
) -> dict[str, Any]:
    current_state = read_session_state(vault, scenario_id, session_id)
    patch = parse_patch_output(patch_output)
    validate_state_patch(current_state, patch)
    next_state = deep_merge(current_state, patch)
    write_session_state(vault, scenario_id, session_id, next_state)
    return next_state


def apply_session_state_patch_for_turn(
    vault: Vault,
    scenario_id: str,
    session_id: str,
    turn: int,
    patch_output: str | dict[str, Any],
) -> dict[str, Any]:
    next_state = apply_session_state_patch_output(vault, scenario_id, session_id, patch_output)
    write_session_state_snapshot(vault, scenario_id, session_id, turn, next_state)
    return next_state


def parse_patch_output(patch_output: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(patch_output, str):
        _validate_patch_size(patch_output)
        try:
            parsed = json.loads(patch_output)
        except json.JSONDecodeError as exc:
            raise StatePatchError("State patch output must be valid JSON") from exc
    else:
        parsed = patch_output

    if not isinstance(parsed, dict):
        raise StatePatchError("State patch output root must be a JSON object")
    if "patch" not in parsed:
        raise StatePatchError("State patch output must contain 'patch'")
    patch = parsed["patch"]
    if not isinstance(patch, dict):
        raise StatePatchError("State patch field must be a JSON object")
    _validate_patch_size(patch)
    _validate_safe_json_value(patch, path="patch")
    return patch


def validate_state_patch(current: dict[str, Any], patch: dict[str, Any]) -> None:
    if not isinstance(current, dict) or not isinstance(patch, dict):
        raise StatePatchError("State and patch must both be JSON objects")
    _validate_patch_types(current, patch, path="patch")


def deep_merge(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(current, dict) or not isinstance(patch, dict):
        raise StatePatchError("State and patch must both be JSON objects")

    merged = dict(current)
    for key, patch_value in patch.items():
        current_value = merged.get(key)
        if isinstance(current_value, dict) and isinstance(patch_value, dict):
            merged[key] = deep_merge(current_value, patch_value)
        else:
            merged[key] = patch_value
    return merged


def _validate_patch_size(value: str | dict[str, Any]) -> None:
    if isinstance(value, str):
        size = len(value.encode("utf-8"))
    else:
        size = len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if size > MAX_STATE_PATCH_BYTES:
        raise StatePatchError("State patch output exceeds 64KB")


def _validate_safe_json_value(value: Any, *, path: str) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise StatePatchError(f"State patch key must be a string at {path}")
            if key in DANGEROUS_STATE_KEYS:
                raise StatePatchError(f"State patch contains dangerous key: {key}")
            _validate_safe_json_value(child, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _validate_safe_json_value(child, path=f"{path}[{index}]")
        return
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    raise StatePatchError(f"State patch contains unsupported value at {path}")


def _validate_patch_types(current: dict[str, Any], patch: dict[str, Any], *, path: str) -> None:
    for key, patch_value in patch.items():
        if key not in current:
            continue
        current_value = current[key]
        if isinstance(current_value, dict) and isinstance(patch_value, dict):
            _validate_patch_types(current_value, patch_value, path=f"{path}.{key}")
            continue
        if isinstance(current_value, dict) != isinstance(patch_value, dict):
            raise StatePatchError(f"State patch would change object type at {path}.{key}")
        if isinstance(current_value, list) != isinstance(patch_value, list):
            raise StatePatchError(f"State patch would change array type at {path}.{key}")
        if _json_scalar_type(current_value) != _json_scalar_type(patch_value):
            raise StatePatchError(f"State patch would change value type at {path}.{key}")


def _json_scalar_type(value: Any) -> type | tuple[type, ...] | None:
    if isinstance(value, dict) or isinstance(value, list):
        return None
    if isinstance(value, bool):
        return bool
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return (int, float)
    if value is None:
        return type(None)
    return type(value)


def create_session(
    vault: Vault,
    metadata: SessionMetadata,
    initial_state_vault_path: str | None = None,
) -> dict[str, Any]:
    _validate_id(metadata.scenario_id, "scenario")
    _validate_id(metadata.session_id, "session")
    data = metadata.to_json()
    if data["turn_count"] < 0:
        raise StateSessionError("turn_count must not be negative")

    session_dir = _session_dir(vault, metadata.scenario_id, metadata.session_id)
    metadata_path = vault.resolve(_session_metadata_path(metadata.scenario_id, metadata.session_id))
    if metadata_path.exists():
        raise StateSessionError(f"Session metadata already exists: {metadata.session_id}")
    session_dir.mkdir(parents=True, exist_ok=True)
    initialize_session_state(vault, metadata.scenario_id, metadata.session_id, initial_state_vault_path)
    _write_json_file(vault, _session_metadata_path(metadata.scenario_id, metadata.session_id), data)
    log_path = vault.resolve(_session_log_path(metadata.scenario_id, metadata.session_id))
    log_path.touch(exist_ok=True)
    return data


def read_session_metadata(vault: Vault, scenario_id: str, session_id: str) -> dict[str, Any]:
    _validate_id(scenario_id, "scenario")
    _validate_id(session_id, "session")
    metadata = vault.load_json(_session_metadata_path(scenario_id, session_id))
    if not isinstance(metadata, dict):
        raise StateSessionError("Session metadata must be a JSON object")
    return metadata


def list_session_metadata(vault: Vault, scenario_id: str) -> list[dict[str, Any]]:
    _validate_id(scenario_id, "scenario")
    sessions_dir = vault.resolve(f"rp/scenarios/{scenario_id}/sessions")
    if not sessions_dir.exists():
        return []
    if not sessions_dir.is_dir():
        raise StateSessionError("sessions path is not a directory")

    sessions: list[dict[str, Any]] = []
    for child in sorted(sessions_dir.iterdir(), key=lambda item: item.name):
        if not child.is_dir() or not is_locus_id(child.name):
            continue
        metadata_path = child / "metadata.json"
        if metadata_path.is_file():
            sessions.append(read_session_metadata(vault, scenario_id, child.name))
    return sessions


def delete_session(vault: Vault, scenario_id: str, session_id: str) -> None:
    _validate_id(scenario_id, "scenario")
    _validate_id(session_id, "session")
    session_dir = _session_dir(vault, scenario_id, session_id)
    if not session_dir.exists():
        raise StateSessionError(f"Session does not exist: {session_id}")
    if not session_dir.is_dir():
        raise StateSessionError(f"Session path is not a directory: {session_id}")
    shutil.rmtree(session_dir)


def write_session_metadata(vault: Vault, scenario_id: str, session_id: str, metadata: dict[str, Any]) -> None:
    _validate_id(scenario_id, "scenario")
    _validate_id(session_id, "session")
    if not isinstance(metadata, dict):
        raise StateSessionError("Session metadata must be a JSON object")
    _write_json_file(vault, _session_metadata_path(scenario_id, session_id), metadata)


def read_latest_session_prompt(vault: Vault, scenario_id: str, session_id: str) -> dict[str, Any] | None:
    _validate_id(scenario_id, "scenario")
    _validate_id(session_id, "session")
    path = vault.resolve(_session_latest_prompt_path(scenario_id, session_id))
    if not path.exists():
        return None
    prompt = vault.load_json(_session_latest_prompt_path(scenario_id, session_id))
    if not isinstance(prompt, dict):
        raise StateSessionError("Session latest prompt must be a JSON object")
    return prompt


def write_latest_session_prompt(
    vault: Vault,
    scenario_id: str,
    session_id: str,
    prompt: dict[str, Any],
) -> None:
    _validate_id(scenario_id, "scenario")
    _validate_id(session_id, "session")
    if not isinstance(prompt, dict):
        raise StateSessionError("Session latest prompt must be a JSON object")
    _write_json_file(vault, _session_latest_prompt_path(scenario_id, session_id), prompt)


def read_session_log(vault: Vault, scenario_id: str, session_id: str, limit: int | None = None) -> list[dict[str, Any]]:
    _validate_id(scenario_id, "scenario")
    _validate_id(session_id, "session")
    if limit is not None and limit < 0:
        raise StateSessionError("limit must not be negative")

    path = vault.resolve(_session_log_path(scenario_id, session_id))
    if not path.exists():
        return []

    entries: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise StateSessionError(f"Invalid session log JSON at line {line_number}") from exc
        if not isinstance(entry, dict):
            raise StateSessionError(f"Session log entry must be an object at line {line_number}")
        entries.append(entry)

    if limit is None:
        return entries
    return entries[-limit:]


def append_session_log(
    vault: Vault,
    scenario_id: str,
    session_id: str,
    *,
    turn: int,
    role: str,
    content: str,
    timestamp: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _validate_id(scenario_id, "scenario")
    _validate_id(session_id, "session")
    if turn < 0:
        raise StateSessionError("turn must not be negative")
    if role not in CHAT_ROLES:
        raise StateSessionError(f"Unsupported log role: {role}")
    if not isinstance(content, str):
        raise StateSessionError("log content must be a string")

    entry: dict[str, Any] = {
        "turn": turn,
        "role": role,
        "content": content,
        "timestamp": timestamp or _now_iso(),
    }
    if extra:
        entry.update(extra)

    path = vault.resolve(_session_log_path(scenario_id, session_id))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
    return entry


def write_session_log(vault: Vault, scenario_id: str, session_id: str, entries: list[dict[str, Any]]) -> None:
    _validate_id(scenario_id, "scenario")
    _validate_id(session_id, "session")
    path = vault.resolve(_session_log_path(scenario_id, session_id))
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as file:
            for entry in entries:
                file.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def update_session_log_entry(
    vault: Vault,
    scenario_id: str,
    session_id: str,
    turn: int,
    role: str,
    updates: dict[str, Any],
) -> dict[str, Any] | None:
    entries = read_session_log(vault, scenario_id, session_id)
    updated_entry = None
    for entry in entries:
        if entry.get("turn") == turn and entry.get("role") == role:
            entry.update(updates)
            updated_entry = entry
            break
    if updated_entry:
        write_session_log(vault, scenario_id, session_id, entries)
    return updated_entry


def delete_session_log_entry(
    vault: Vault,
    scenario_id: str,
    session_id: str,
    turn: int,
    role: str,
) -> bool:
    entries = read_session_log(vault, scenario_id, session_id)
    initial_len = len(entries)
    entries = [e for e in entries if not (e.get("turn") == turn and e.get("role") == role)]
    if len(entries) < initial_len:
        write_session_log(vault, scenario_id, session_id, entries)
        return True
    return False


def delete_session_log_from_turn(
    vault: Vault,
    scenario_id: str,
    session_id: str,
    turn: int,
) -> bool:
    entries = read_session_log(vault, scenario_id, session_id)
    initial_len = len(entries)
    entries = [e for e in entries if e.get("turn", 0) < turn]
    if len(entries) < initial_len:
        write_session_log(vault, scenario_id, session_id, entries)
        return True
    return False


def next_session_id(vault: Vault, scenario_id: str) -> str:
    _validate_id(scenario_id, "scenario")
    sessions_dir = vault.resolve(f"rp/scenarios/{scenario_id}/sessions")
    if not sessions_dir.exists():
        return "session_001"
    if not sessions_dir.is_dir():
        raise StateSessionError("sessions path is not a directory")

    max_index = 0
    for child in sessions_dir.iterdir():
        if child.is_dir() and child.name.startswith("session_"):
            suffix = child.name.removeprefix("session_")
            if suffix.isdigit():
                max_index = max(max_index, int(suffix))
    return f"session_{max_index + 1:03d}"


def _write_json_file(vault: Vault, relative_path: str, data: dict[str, Any]) -> None:
    path = vault.resolve(relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        temp_path.write_text(raw, encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _initial_state_path(scenario_id: str) -> str:
    return f"rp/scenarios/{scenario_id}/state/current.json"


def _session_state_path(scenario_id: str, session_id: str) -> str:
    return f"rp/scenarios/{scenario_id}/sessions/{session_id}/state/current.json"


def _session_state_snapshot_path(scenario_id: str, session_id: str, turn: int) -> str:
    return f"rp/scenarios/{scenario_id}/sessions/{session_id}/state/snapshots/turn_{turn:04d}.json"


def _session_metadata_path(scenario_id: str, session_id: str) -> str:
    return f"rp/scenarios/{scenario_id}/sessions/{session_id}/metadata.json"


def _session_log_path(scenario_id: str, session_id: str) -> str:
    return f"rp/scenarios/{scenario_id}/sessions/{session_id}/log.jsonl"


def _session_latest_prompt_path(scenario_id: str, session_id: str) -> str:
    return f"rp/scenarios/{scenario_id}/sessions/{session_id}/prompt/latest.json"


def _session_dir(vault: Vault, scenario_id: str, session_id: str) -> Path:
    return vault.resolve(f"rp/scenarios/{scenario_id}/sessions/{session_id}")


def _validate_id(value: str, kind: str) -> None:
    if not is_locus_id(value):
        raise StateSessionError(f"Invalid {kind} id: {value}")


def _validate_turn(turn: int) -> None:
    if not isinstance(turn, int) or turn < 0:
        raise StateSessionError("turn must be a non-negative integer")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

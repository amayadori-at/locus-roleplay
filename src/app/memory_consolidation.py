from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from app.ids import is_locus_id
from app.loaders import ModelProfile, load_profile, load_scenario
from app.memory_summarizer import mark_rag_index_stale
from app.model_client import ChatCompletionResult
from app.reasoning import sanitize_log_entries
from app.state_session import read_session_log, read_session_state
from app.vault import Vault, VaultError, VaultFileError


ALLOWED_SOURCE_MEMORY_KINDS = frozenset({"session_summaries", "extracted_facts", "unresolved_threads"})
SUGGESTION_FOLDER = "consolidation_suggestions"
SUGGESTION_STATUS_VALUES = frozenset({"pending", "accepted", "rejected", "applied"})
APPLICABLE_MEMORY_STATUS_VALUES = frozenset({"active", "resolved", "superseded", "stale", "archived"})


class MemoryConsolidationError(VaultError):
    """Raised when memory consolidation suggestions cannot be safely handled."""


class MemoryConsolidationClient(Protocol):
    def create_chat_completion(
        self, profile: ModelProfile | dict[str, Any], messages: list[dict[str, str]]
    ) -> ChatCompletionResult:
        ...


@dataclass(frozen=True)
class MemoryConsolidationResult:
    created_files: list[str]
    suggestions: list[dict[str, Any]]
    messages: list[dict[str, str]]
    raw_output: str


@dataclass(frozen=True)
class MemoryConsolidationApplyResult:
    suggestion: dict[str, Any]
    updated_memory_paths: list[str]
    stale_paths: list[str]


def run_memory_consolidation(
    vault: Vault,
    *,
    scenario_id: str,
    session_id: str,
    profile_id: str,
    model_client: MemoryConsolidationClient,
    recent_log_limit: int = 24,
) -> MemoryConsolidationResult:
    if not is_locus_id(scenario_id):
        raise MemoryConsolidationError(f"Invalid scenario id: {scenario_id}")
    if not is_locus_id(session_id):
        raise MemoryConsolidationError(f"Invalid session id: {session_id}")
    scenario = load_scenario(vault, scenario_id)
    profile = load_profile(vault, profile_id)
    memory_items = _source_memory_items(vault, scenario_id)
    messages = compose_memory_consolidation_messages(
        scenario_id=scenario_id,
        session_id=session_id,
        scenario_metadata=scenario.metadata,
        memory_items=memory_items,
        current_state=read_session_state(vault, scenario_id, session_id),
        recent_log=sanitize_log_entries(read_session_log(vault, scenario_id, session_id))[-recent_log_limit:],
    )
    completion = model_client.create_chat_completion(profile, messages)
    suggestions = parse_consolidation_output(completion.content, scenario_id=scenario_id)
    created_files = write_consolidation_suggestions(vault, scenario_id=scenario_id, session_id=session_id, suggestions=suggestions)
    if created_files:
        mark_rag_index_stale(vault, scenario_id, created_files)
    return MemoryConsolidationResult(
        created_files=created_files,
        suggestions=suggestions,
        messages=messages,
        raw_output=completion.content,
    )


def list_consolidation_suggestions(vault: Vault, scenario_id: str) -> list[dict[str, Any]]:
    if not is_locus_id(scenario_id):
        raise MemoryConsolidationError(f"Invalid scenario id: {scenario_id}")
    load_scenario(vault, scenario_id)
    base = vault.resolve(f"rp/scenarios/{scenario_id}")
    directory = base / "memory" / SUGGESTION_FOLDER
    if not directory.is_dir():
        return []
    suggestions: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.md")):
        scenario_relative = path.relative_to(base).as_posix()
        try:
            document = vault.load_markdown(f"rp/scenarios/{scenario_id}/{scenario_relative}")
        except VaultFileError as exc:
            raise MemoryConsolidationError(f"consolidation suggestion is unreadable: {scenario_relative}") from exc
        metadata = dict(document.frontmatter)
        suggestions.append(_suggestion_item(path, scenario_relative, metadata, document.body))
    suggestions.sort(key=lambda item: (-item["updated_at"], item["path"]))
    return suggestions


def update_consolidation_suggestion_status(
    vault: Vault,
    *,
    scenario_id: str,
    suggestion_id: str,
    status: str,
) -> dict[str, Any]:
    if status not in SUGGESTION_STATUS_VALUES:
        raise MemoryConsolidationError(f"Invalid suggestion status: {status!r}")
    path, scenario_relative, metadata, body = _load_suggestion(vault, scenario_id, suggestion_id)
    metadata["status"] = status
    _atomic_write_text(path, _markdown(metadata, body))
    mark_rag_index_stale(vault, scenario_id, [scenario_relative])
    return _suggestion_item(path, scenario_relative, metadata, body)


def apply_consolidation_suggestion(
    vault: Vault,
    *,
    scenario_id: str,
    suggestion_id: str,
) -> MemoryConsolidationApplyResult:
    suggestion_path, suggestion_relative, metadata, body = _load_suggestion(vault, scenario_id, suggestion_id)
    suggestion = _suggestion_item(suggestion_path, suggestion_relative, metadata, body)
    if suggestion["status"] != "accepted":
        raise MemoryConsolidationError("Consolidation suggestion must be accepted before apply")
    staged = _stage_actions(vault, scenario_id, suggestion["suggested_actions"])
    updated_paths = _write_staged_memory_updates(staged)
    metadata["status"] = "applied"
    _atomic_write_text(suggestion_path, _markdown(metadata, body))
    stale_paths = [*updated_paths, suggestion_relative]
    mark_rag_index_stale(vault, scenario_id, stale_paths)
    updated_suggestion = _suggestion_item(suggestion_path, suggestion_relative, metadata, body)
    return MemoryConsolidationApplyResult(
        suggestion=updated_suggestion,
        updated_memory_paths=updated_paths,
        stale_paths=stale_paths,
    )


def compose_memory_consolidation_messages(
    *,
    scenario_id: str,
    session_id: str,
    scenario_metadata: dict[str, Any],
    memory_items: list[dict[str, Any]],
    current_state: dict[str, Any],
    recent_log: list[dict[str, Any]],
) -> list[dict[str, str]]:
    system_content = "\n".join(
        (
            "You review generated long-term memory for a roleplay scenario.",
            "Return valid JSON only. Do not use Markdown fences or explanations.",
            "Do not rewrite scenario, lore, character, persona, or profile files.",
            "Suggest changes only for memory/**/*.md files listed in the input.",
            "Suggestions are proposals; they will not be applied automatically.",
        )
    )
    expected_shape = {
        "suggestions": [
            {
                "title": "短い提案タイトル",
                "summary": "重複、矛盾、解決済み、陳腐化などの理由。",
                "affected_memory_paths": ["memory/session_summaries/example.md"],
                "suggested_actions": [
                    {"action": "set_status", "path": "memory/unresolved_threads/example.md", "status": "resolved"}
                ],
            }
        ]
    }
    user_content = "\n\n".join(
        (
            _section("Scenario", scenario_id),
            _section("Session", session_id),
            _section("Scenario metadata", json.dumps(scenario_metadata, ensure_ascii=False, indent=2, sort_keys=True)),
            _section("Current session state", json.dumps(current_state, ensure_ascii=False, indent=2, sort_keys=True)),
            _section("Recent session log", json.dumps(recent_log, ensure_ascii=False, indent=2, sort_keys=True)),
            _section("Memory files", json.dumps(memory_items, ensure_ascii=False, indent=2, sort_keys=True)),
            _section("Expected JSON shape", json.dumps(expected_shape, ensure_ascii=False, indent=2)),
        )
    )
    return [{"role": "system", "content": system_content}, {"role": "user", "content": user_content}]


def parse_consolidation_output(raw_output: str, *, scenario_id: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise MemoryConsolidationError("Memory consolidation output must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise MemoryConsolidationError("Memory consolidation output root must be a JSON object")
    raw_suggestions = parsed.get("suggestions", [])
    if not isinstance(raw_suggestions, list):
        raise MemoryConsolidationError("suggestions must be an array")
    suggestions: list[dict[str, Any]] = []
    for index, item in enumerate(raw_suggestions, start=1):
        if not isinstance(item, dict):
            raise MemoryConsolidationError("each suggestion must be an object")
        title = _non_empty_string(item.get("title")) or f"Memory consolidation suggestion {index}"
        summary = _non_empty_string(item.get("summary")) or ""
        affected_paths = _validate_memory_paths(item.get("affected_memory_paths", []), field="affected_memory_paths")
        actions = _validate_actions(item.get("suggested_actions", []))
        if not affected_paths and actions:
            affected_paths = sorted({action["path"] for action in actions if isinstance(action.get("path"), str)})
        if not affected_paths:
            raise MemoryConsolidationError("suggestion must affect at least one memory path")
        suggestions.append(
            {
                "id": _suggestion_id(scenario_id, index),
                "title": title,
                "summary": summary,
                "affected_memory_paths": affected_paths,
                "suggested_actions": actions,
            }
        )
    return suggestions


def write_consolidation_suggestions(
    vault: Vault,
    *,
    scenario_id: str,
    session_id: str,
    suggestions: list[dict[str, Any]],
) -> list[str]:
    base = vault.resolve(f"rp/scenarios/{scenario_id}/memory/{SUGGESTION_FOLDER}")
    base.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    created_at = _utc_timestamp()
    for suggestion in suggestions:
        suggestion_id = _safe_suggestion_id(str(suggestion["id"]))
        path = base / f"{suggestion_id}.md"
        metadata = {
            "type": "memory_consolidation_suggestion",
            "scenario": scenario_id,
            "session_id": session_id,
            "source": "model_consolidation",
            "created": created_at,
            "status": "pending",
            "rag": False,
            "affected_memory_paths": suggestion["affected_memory_paths"],
            "suggested_actions": [_json_action(action) for action in suggestion["suggested_actions"]],
        }
        body = _suggestion_body(suggestion)
        _atomic_write_text(path, _markdown(metadata, body))
        created.append(f"memory/{SUGGESTION_FOLDER}/{suggestion_id}.md")
    return created


def _source_memory_items(vault: Vault, scenario_id: str) -> list[dict[str, Any]]:
    base = vault.resolve(f"rp/scenarios/{scenario_id}")
    root = base / "memory"
    items: list[dict[str, Any]] = []
    for kind in sorted(ALLOWED_SOURCE_MEMORY_KINDS):
        directory = root / kind
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            scenario_relative = path.relative_to(base).as_posix()
            try:
                document = vault.load_markdown(f"rp/scenarios/{scenario_id}/{scenario_relative}")
            except VaultFileError as exc:
                raise MemoryConsolidationError(f"memory markdown is unreadable: {scenario_relative}") from exc
            items.append(
                {
                    "path": scenario_relative,
                    "metadata": document.frontmatter,
                    "content": document.body.strip(),
                }
            )
    return items


def _suggestion_item(path: Path, scenario_relative: str, metadata: dict[str, Any], body: str) -> dict[str, Any]:
    actions = [_parse_action_string(value) for value in _string_list(metadata.get("suggested_actions"))]
    actions = [action for action in actions if action is not None]
    return {
        "id": path.stem,
        "path": scenario_relative,
        "title": str(metadata.get("title") or path.stem),
        "status": _suggestion_status(metadata.get("status")),
        "source": metadata.get("source") if isinstance(metadata.get("source"), str) else "model_consolidation",
        "session_id": metadata.get("session_id") if isinstance(metadata.get("session_id"), str) else "",
        "created": metadata.get("created") if isinstance(metadata.get("created"), str) else "",
        "affected_memory_paths": _string_list(metadata.get("affected_memory_paths")),
        "suggested_actions": actions,
        "content": body.strip(),
        "updated_at": path.stat().st_mtime,
    }


def _load_suggestion(
    vault: Vault,
    scenario_id: str,
    suggestion_id: str,
) -> tuple[Path, str, dict[str, Any], str]:
    if not is_locus_id(scenario_id):
        raise MemoryConsolidationError(f"Invalid scenario id: {scenario_id}")
    suggestion_id = _safe_suggestion_id(suggestion_id)
    load_scenario(vault, scenario_id)
    scenario_relative = f"memory/{SUGGESTION_FOLDER}/{suggestion_id}.md"
    path = vault.resolve(f"rp/scenarios/{scenario_id}/{scenario_relative}")
    if not path.is_file():
        raise MemoryConsolidationError(f"Consolidation suggestion not found: {suggestion_id}")
    try:
        document = vault.load_markdown(f"rp/scenarios/{scenario_id}/{scenario_relative}")
    except VaultFileError as exc:
        raise MemoryConsolidationError(f"consolidation suggestion is unreadable: {scenario_relative}") from exc
    metadata = dict(document.frontmatter)
    if metadata.get("type") != "memory_consolidation_suggestion":
        raise MemoryConsolidationError(f"Not a consolidation suggestion: {suggestion_id}")
    return path, scenario_relative, metadata, document.body


def _stage_actions(
    vault: Vault,
    scenario_id: str,
    actions: list[dict[str, Any]],
) -> dict[str, tuple[Path, dict[str, Any], dict[str, Any], str]]:
    staged: dict[str, tuple[Path, dict[str, Any], dict[str, Any], str]] = {}
    for action in actions:
        memory_path = _validate_memory_path(action.get("path"))
        if memory_path not in staged:
            path, metadata, body = _load_memory_file(vault, scenario_id, memory_path)
            staged[memory_path] = (path, dict(metadata), metadata, body)
        _apply_action_to_metadata(staged[memory_path][2], action)
    return staged


def _write_staged_memory_updates(staged: dict[str, tuple[Path, dict[str, Any], dict[str, Any], str]]) -> list[str]:
    updated_paths: list[str] = []
    for memory_path, (path, original_metadata, metadata, body) in staged.items():
        if metadata == original_metadata:
            continue
        _atomic_write_text(path, _markdown(metadata, body))
        updated_paths.append(memory_path)
    return updated_paths


def _apply_action(vault: Vault, scenario_id: str, action: dict[str, Any]) -> list[str]:
    action_type = action.get("action")
    memory_path = _validate_memory_path(action.get("path"))
    path, metadata, body = _load_memory_file(vault, scenario_id, memory_path)
    before = dict(metadata)
    _apply_action_to_metadata(metadata, action)
    if metadata == before:
        return []
    _atomic_write_text(path, _markdown(metadata, body))
    return [memory_path]


def _apply_action_to_metadata(metadata: dict[str, Any], action: dict[str, Any]) -> None:
    action_type = action.get("action")
    if action_type == "set_status":
        status = action.get("status")
        if not isinstance(status, str) or status not in APPLICABLE_MEMORY_STATUS_VALUES:
            raise MemoryConsolidationError("set_status action requires a valid status")
        metadata["status"] = status
        if status == "resolved" and not metadata.get("resolved_at"):
            metadata["resolved_at"] = _utc_timestamp()
    elif action_type == "set_supersedes":
        metadata["supersedes"] = _validate_memory_paths(action.get("supersedes", []), field="supersedes")
    elif action_type == "set_superseded_by":
        metadata["superseded_by"] = _validate_memory_paths(action.get("superseded_by", []), field="superseded_by")
    else:
        raise MemoryConsolidationError(f"Unsupported suggested action: {action_type!r}")


def _load_memory_file(vault: Vault, scenario_id: str, memory_path: str) -> tuple[Path, dict[str, Any], str]:
    memory_path = _validate_memory_path(memory_path)
    path = vault.resolve(f"rp/scenarios/{scenario_id}/{memory_path}")
    if not path.is_file():
        raise MemoryConsolidationError(f"Memory file not found: {memory_path}")
    try:
        document = vault.load_markdown(f"rp/scenarios/{scenario_id}/{memory_path}")
    except VaultFileError as exc:
        raise MemoryConsolidationError(f"memory markdown is unreadable: {memory_path}") from exc
    return path, dict(document.frontmatter), document.body


def _validate_actions(value: object) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise MemoryConsolidationError("suggested_actions must be an array of objects")
    actions: list[dict[str, Any]] = []
    for item in value:
        action = item.get("action")
        path = item.get("path")
        if action == "set_status":
            if not isinstance(item.get("status"), str) or item["status"] not in APPLICABLE_MEMORY_STATUS_VALUES:
                raise MemoryConsolidationError("set_status action requires a valid status")
            actions.append({"action": "set_status", "path": _validate_memory_path(path), "status": item["status"]})
        elif action == "set_supersedes":
            actions.append(
                {
                    "action": "set_supersedes",
                    "path": _validate_memory_path(path),
                    "supersedes": _validate_memory_paths(item.get("supersedes", []), field="supersedes"),
                }
            )
        elif action == "set_superseded_by":
            actions.append(
                {
                    "action": "set_superseded_by",
                    "path": _validate_memory_path(path),
                    "superseded_by": _validate_memory_paths(item.get("superseded_by", []), field="superseded_by"),
                }
            )
        else:
            raise MemoryConsolidationError(f"Unsupported suggested action: {action!r}")
    return actions


def _validate_memory_paths(value: object, *, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise MemoryConsolidationError(f"{field} must be an array")
    return [_validate_memory_path(path) for path in value]


def _validate_memory_path(value: object) -> str:
    if not isinstance(value, str):
        raise MemoryConsolidationError("memory path must be a string")
    if value.startswith("/") or "\\" in value:
        raise MemoryConsolidationError(f"Unsafe memory path: {value!r}")
    parts = value.split("/")
    if len(parts) != 3 or parts[0] != "memory" or parts[1] not in ALLOWED_SOURCE_MEMORY_KINDS:
        raise MemoryConsolidationError(f"Unsupported memory path: {value!r}")
    if any(part in {"", ".", ".."} for part in parts):
        raise MemoryConsolidationError(f"Unsafe memory path: {value!r}")
    if not parts[2].endswith(".md") or not re.fullmatch(r"[A-Za-z0-9_.-]+\.md", parts[2]):
        raise MemoryConsolidationError(f"Invalid memory filename: {value!r}")
    return value


def _parse_action_string(value: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    try:
        return _validate_actions([parsed])[0]
    except MemoryConsolidationError:
        return None


def _json_action(action: dict[str, Any]) -> str:
    return json.dumps(action, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _suggestion_status(value: object) -> str:
    return value if isinstance(value, str) and value in SUGGESTION_STATUS_VALUES else "pending"


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _non_empty_string(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _suggestion_id(scenario_id: str, index: int) -> str:
    return f"{scenario_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}_{index:02d}"


def _safe_suggestion_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
        raise MemoryConsolidationError(f"Invalid suggestion id: {value!r}")
    return value


def _suggestion_body(suggestion: dict[str, Any]) -> str:
    lines = [f"# {suggestion['title']}", "", suggestion.get("summary", "").strip()]
    if suggestion.get("suggested_actions"):
        lines.extend(("", "## Suggested Actions", ""))
        for action in suggestion["suggested_actions"]:
            lines.append(f"- `{_json_action(action)}`")
    return "\n".join(line for line in lines if line is not None).strip()


def _section(title: str, body: str) -> str:
    return f"## {title}\n{body.strip() if body.strip() else '(empty)'}"


def _markdown(frontmatter: dict[str, Any], body: str) -> str:
    return "---\n" + "\n".join(_yaml_lines(frontmatter)) + "\n---\n\n" + body.strip() + "\n"


def _yaml_lines(data: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {_yaml_scalar(item)}")
        else:
            lines.append(f"{key}: {_yaml_scalar(value)}")
    return lines


def _yaml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return str(value)
    text = str(value)
    if not text:
        return '""'
    if re.fullmatch(r"[A-Za-z0-9_./:+-]+", text):
        return text
    if "'" not in text:
        return f"'{text}'"
    return json.dumps(text, ensure_ascii=False)


def _atomic_write_text(path: Path, content: str) -> None:
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

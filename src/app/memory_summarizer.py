from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from app.ids import is_locus_id
from app.loaders import ModelProfile, load_profile, load_scenario
from app.model_client import ChatCompletionResult
from app.reasoning import sanitize_log_entries
from app.state_session import read_session_log, read_session_state
from app.vault import Vault, VaultError, VaultPathError


DEFAULT_MEMORY_UPDATE_INTERVAL_TURNS = 4


class MemorySummaryError(VaultError):
    """Raised when memory summarization cannot produce safe memory files."""


class MemorySummaryClient(Protocol):
    def create_chat_completion(
        self, profile: ModelProfile | dict[str, Any], messages: list[dict[str, str]]
    ) -> ChatCompletionResult:
        ...


@dataclass(frozen=True)
class MemorySummaryContext:
    scenario_id: str
    session_id: str
    turn: int
    start_turn: int
    end_turn: int
    current_state: dict[str, Any]
    recent_turns: list[dict[str, Any]]


@dataclass(frozen=True)
class MemorySummaryResult:
    created_files: list[str]
    messages: list[dict[str, str]]
    raw_output: str


def memory_update_interval_turns(scenario_metadata: dict[str, Any]) -> int:
    value = scenario_metadata.get("memory_update_interval_turns", DEFAULT_MEMORY_UPDATE_INTERVAL_TURNS)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        return DEFAULT_MEMORY_UPDATE_INTERVAL_TURNS
    return value


def should_update_memory(scenario_metadata: dict[str, Any], turn: int) -> bool:
    if not isinstance(turn, int) or turn <= 0:
        return False
    interval = memory_update_interval_turns(scenario_metadata)
    return turn % interval == 0


def run_memory_summary(
    vault: Vault,
    *,
    scenario_id: str,
    session_id: str,
    turn: int,
    profile_id: str,
    model_client: MemorySummaryClient,
) -> MemorySummaryResult:
    if not is_locus_id(scenario_id):
        raise MemorySummaryError(f"Invalid scenario id: {scenario_id}")
    if not is_locus_id(session_id):
        raise MemorySummaryError(f"Invalid session id: {session_id}")
    scenario = load_scenario(vault, scenario_id)
    profile = load_profile(vault, profile_id)
    interval = memory_update_interval_turns(scenario.metadata)
    start_turn = 0 if turn <= interval else turn - interval + 1
    recent_turns = _turn_entries(sanitize_log_entries(read_session_log(vault, scenario_id, session_id)), start_turn, turn)
    if not recent_turns:
        raise MemorySummaryError("No session log entries are available for memory summarization")

    context = MemorySummaryContext(
        scenario_id=scenario_id,
        session_id=session_id,
        turn=turn,
        start_turn=start_turn,
        end_turn=turn,
        current_state=read_session_state(vault, scenario_id, session_id),
        recent_turns=recent_turns,
    )
    messages = compose_memory_summary_messages(context)
    completion = model_client.create_chat_completion(profile, messages)
    output = parse_memory_summary_output(completion.content)
    created_files = write_memory_summary_files(vault, context, output)
    if created_files:
        mark_rag_index_stale(vault, scenario_id, created_files)
    return MemorySummaryResult(created_files=created_files, messages=messages, raw_output=completion.content)


def compose_memory_summary_messages(context: MemorySummaryContext) -> list[dict[str, str]]:
    system_content = "\n".join(
        (
            "You summarize durable memory for a roleplay session.",
            "Return valid JSON only.",
            "Do not use Markdown fences or explanations.",
            "Keep state and memory separate. Do not output current state JSON.",
            "Only include facts supported by the recent turns.",
            "Use Japanese for content when the session is Japanese.",
            "Output keys: session_summary, facts, relationships, unresolved_threads.",
            "facts, relationships, and unresolved_threads must each be an array of OBJECTS, not strings.",
            "Every array item must be an object with a non-empty \"content\" field (a Japanese sentence).",
            "Do not output bare strings inside these arrays.",
        )
    )
    user_content = "\n\n".join(
        (
            _section("Scenario", context.scenario_id),
            _section("Session", context.session_id),
            _section("Turn range", f"{context.start_turn}-{context.end_turn}"),
            _section("Current state", json.dumps(context.current_state, ensure_ascii=False, indent=2, sort_keys=True)),
            _section("Recent turns", _recent_turns_text(context.recent_turns)),
            _section(
                "Expected JSON shape",
                json.dumps(
                    {
                        "session_summary": {
                            "title": "短いタイトル",
                            "content": "この範囲で起きた重要な出来事。",
                            "characters": [],
                            "locations": [],
                            "topics": [],
                            "importance": 50,
                            "confidence": 0.75,
                        },
                        "facts": [
                            {
                                "content": "持続的な事実を一文で。",
                                "characters": [],
                                "locations": [],
                                "topics": [],
                                "importance": 50,
                            }
                        ],
                        "relationships": [
                            {
                                "source": "character_id",
                                "target": "user",
                                "content": "関係の変化を一文で。",
                                "topics": [],
                                "importance": 50,
                            }
                        ],
                        "unresolved_threads": [
                            {
                                "content": "未解決の伏線を一文で。",
                                "topics": [],
                                "importance": 50,
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            ),
        )
    )
    return [{"role": "system", "content": system_content}, {"role": "user", "content": user_content}]


def parse_memory_summary_output(raw_output: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise MemorySummaryError("Memory summary output must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise MemorySummaryError("Memory summary output root must be a JSON object")

    summary = parsed.get("session_summary")
    facts = parsed.get("facts", [])
    relationships = parsed.get("relationships", [])
    unresolved = parsed.get("unresolved_threads", [])
    if summary is not None and not isinstance(summary, dict):
        raise MemorySummaryError("session_summary must be an object")
    for field, value in (("facts", facts), ("relationships", relationships), ("unresolved_threads", unresolved)):
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            raise MemorySummaryError(f"{field} must be an array of objects")
    for field, value in (
        ("session_summary", [summary] if summary is not None else []),
        ("facts", facts),
        ("relationships", relationships),
        ("unresolved_threads", unresolved),
    ):
        for item in value:
            if isinstance(item, dict):
                _validate_confidence(field, item.get("confidence"))
    return {
        "session_summary": summary,
        "facts": facts,
        "relationships": relationships,
        "unresolved_threads": unresolved,
    }


def write_memory_summary_files(vault: Vault, context: MemorySummaryContext, output: dict[str, Any]) -> list[str]:
    created: list[str] = []
    summary = output.get("session_summary")
    if isinstance(summary, dict) and _item_content(summary):
        created.append(
            _write_memory_file(
                vault,
                context,
                folder="session_summaries",
                filename=f"{context.session_id}_turns_{context.start_turn:04d}_{context.end_turn:04d}.md",
                memory_kind="session_summary",
                item=summary,
            )
        )

    for index, item in enumerate(output.get("facts", []), start=1):
        if isinstance(item, dict) and _item_content(item):
            created.append(
                _write_memory_file(
                    vault,
                    context,
                    folder="extracted_facts",
                    filename=f"{context.session_id}_turns_{context.start_turn:04d}_{context.end_turn:04d}_fact_{index:03d}.md",
                    memory_kind="fact",
                    item=item,
                )
            )

    for index, item in enumerate(output.get("relationships", []), start=1):
        if isinstance(item, dict) and _item_content(item):
            created.append(
                _write_memory_file(
                    vault,
                    context,
                    folder="extracted_facts",
                    filename=(
                        f"{context.session_id}_turns_{context.start_turn:04d}_{context.end_turn:04d}"
                        f"_relationship_{index:03d}.md"
                    ),
                    memory_kind="relationship",
                    item=item,
                )
            )

    for index, item in enumerate(output.get("unresolved_threads", []), start=1):
        if isinstance(item, dict) and _item_content(item):
            created.append(
                _write_memory_file(
                    vault,
                    context,
                    folder="unresolved_threads",
                    filename=f"{context.session_id}_turns_{context.start_turn:04d}_{context.end_turn:04d}_thread_{index:03d}.md",
                    memory_kind="unresolved_thread",
                    item=item,
                )
            )
    return created


def mark_rag_index_stale(
    vault: Vault,
    scenario_id: str,
    created_files: list[str],
    *,
    reason: str = "memory_files_created",
) -> None:
    if not is_locus_id(scenario_id):
        raise MemorySummaryError(f"Invalid scenario id: {scenario_id}")
    path = vault.resolve("rp/_cache/rag/stale.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "scenario_id": scenario_id,
        "reason": reason,
        "created_files": created_files,
        "marked_at": _now_iso(),
    }
    if reason == "memory_files_deleted":
        payload["deleted_files"] = created_files
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_memory_file(
    vault: Vault,
    context: MemorySummaryContext,
    *,
    folder: str,
    filename: str,
    memory_kind: str,
    item: dict[str, Any],
) -> str:
    relative_path = _unique_memory_path(vault, context.scenario_id, folder, filename)
    frontmatter = {
        "type": "memory",
        "memory_kind": memory_kind,
        "scenario": context.scenario_id,
        "session_id": context.session_id,
        "turn_range": f"{context.start_turn}-{context.end_turn}",
        "characters": _string_list(item.get("characters")),
        "locations": _string_list(item.get("locations")),
        "topics": _string_list(item.get("topics")),
        "importance": _importance(item.get("importance")),
        "status": "active",
        "source": "model_summary",
        "last_seen_turn": context.end_turn,
        "rag": True,
        "created": _now_iso(),
    }
    confidence = _confidence(item.get("confidence"))
    if confidence is not None:
        frontmatter["confidence"] = confidence
    content = _item_content(item)
    raw = _markdown(frontmatter, content)
    path = vault.resolve(relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(raw, encoding="utf-8")
    return _scenario_relative_memory_path(context.scenario_id, relative_path)


def _unique_memory_path(vault: Vault, scenario_id: str, folder: str, filename: str) -> str:
    if not is_locus_id(scenario_id):
        raise MemorySummaryError(f"Invalid scenario id: {scenario_id}")
    if not is_locus_id(folder):
        raise MemorySummaryError(f"Invalid memory folder: {folder}")
    if not re.fullmatch(r"[A-Za-z0-9_]+\.md", filename):
        raise MemorySummaryError(f"Invalid memory filename: {filename}")
    stem = filename.removesuffix(".md")
    candidate = f"rp/scenarios/{scenario_id}/memory/{folder}/{filename}"
    counter = 2
    while vault.resolve(candidate).exists():
        candidate = f"rp/scenarios/{scenario_id}/memory/{folder}/{stem}_{counter:03d}.md"
        counter += 1
    try:
        vault.resolve(candidate).relative_to(vault.resolve(f"rp/scenarios/{scenario_id}/memory"))
    except (ValueError, VaultPathError) as exc:
        raise MemorySummaryError("Memory path escapes the scenario memory directory") from exc
    return candidate


def _scenario_relative_memory_path(scenario_id: str, relative_path: str) -> str:
    prefix = f"rp/scenarios/{scenario_id}/"
    return relative_path.removeprefix(prefix)


def _validate_confidence(field: str, value: object) -> None:
    if value is None:
        return
    if _confidence(value) is None:
        raise MemorySummaryError(f"{field}.confidence must be a number between 0 and 1")


def _confidence(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    confidence = float(value)
    if confidence < 0 or confidence > 1:
        return None
    return round(confidence, 3)


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
    if isinstance(value, int):
        return str(value)
    text = str(value)
    if not text:
        return '""'
    if re.fullmatch(r"[A-Za-z0-9_./:-]+", text):
        return text
    return json.dumps(text, ensure_ascii=False)


def _turn_entries(entries: list[dict[str, Any]], start_turn: int, end_turn: int) -> list[dict[str, Any]]:
    return [
        entry
        for entry in entries
        if isinstance(entry.get("turn"), int) and start_turn <= entry["turn"] <= end_turn and isinstance(entry.get("content"), str)
    ]


def _recent_turns_text(entries: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for entry in entries:
        lines.append(f"turn {entry.get('turn')} {entry.get('role')}: {entry.get('content')}")
    return "\n".join(lines)


def _item_content(item: dict[str, Any]) -> str:
    value = item.get("content")
    return value.strip() if isinstance(value, str) else ""


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _importance(value: object) -> int:
    if isinstance(value, bool):
        return 50
    if isinstance(value, (int, float)):
        return max(0, min(100, int(value)))
    return 50


def _section(title: str, content: str) -> str:
    stripped = content.strip()
    return f"## {title}\n{stripped}" if stripped else ""


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

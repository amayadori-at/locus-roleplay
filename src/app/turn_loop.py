from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Protocol

from app.loaders import ModelProfile, Persona, Scenario, load_profile, load_scenario
from app.images import Segment, parse_image_markers
from app.messages import is_conversation_role
from app.model_client import ChatCompletionResult
from app.prompt_preview import compose_prompt_graph
from app.state_session import (
    append_session_log,
    read_session_log,
    read_session_metadata,
    write_latest_session_prompt,
    write_session_metadata,
)
from app.turn_postprocess import run_turn_postprocess
from app.turn_prompt_payload import latest_prompt_payload
from app.vault import Vault, VaultError


class TurnLoopError(VaultError):
    """Raised when the GM turn loop cannot run."""


class ChatCompletionClient(Protocol):
    def create_chat_completion(
        self, profile: ModelProfile | dict[str, Any], messages: list[dict[str, str]]
    ) -> ChatCompletionResult:
        ...


class StreamingChatCompletionClient(ChatCompletionClient, Protocol):
    def create_chat_completion_stream(
        self, profile: ModelProfile | dict[str, Any], messages: list[dict[str, str]]
    ) -> Iterable[str]:
        ...


@dataclass(frozen=True)
class PromptContext:
    scenario: Scenario
    persona: Persona
    profile: ModelProfile
    state: dict[str, Any]
    recent_log: list[dict[str, Any]]
    user_note: str = ""


@dataclass(frozen=True)
class TurnResult:
    session_id: str
    scenario_id: str
    turn: int
    assistant_content: str
    messages: list[dict[str, str]]
    segments: list[Segment]
    state_updated: bool = False
    state_update_error: str | None = None
    memory_updated: bool = False
    memory_update_error: str | None = None
    memory_files: list[str] | None = None


@dataclass(frozen=True)
class TurnPreparation:
    metadata: dict[str, Any]
    scenario: Scenario
    profile: ModelProfile
    recent_log: list[dict[str, Any]]
    prompt: dict[str, Any]
    messages: list[dict[str, str]]
    turn: int


def compose_gm_messages(context: PromptContext, user_message: str) -> list[dict[str, str]]:
    if not isinstance(user_message, str) or not user_message.strip():
        raise TurnLoopError("user_message must be a non-empty string")

    system_content = "\n\n".join(
        section
        for section in (
            _section("System Prompt", context.scenario.system_prompt),
            _section("GM Policy", context.scenario.gm_system),
            _section("Narration Policy", context.scenario.narration_policy),
            _section("Scenario", _scenario_text(context.scenario)),
            _section("User Persona", _persona_text(context.persona)),
            _section("Session User Note", context.user_note),
            _section("Current State", _state_text(context.state)),
            _section("Relevant Characters", ""),
            _section("Relevant Lore", ""),
            _section("Relevant Memory", ""),
            _section("Image Policy", _image_policy_text(context.scenario)),
        )
        if section
    )

    messages = [{"role": "system", "content": system_content}]
    for entry in context.recent_log:
        role = entry.get("role")
        content = entry.get("content")
        if is_conversation_role(role) and isinstance(content, str) and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})
    return messages


def run_gm_turn(
    vault: Vault,
    *,
    scenario_id: str,
    session_id: str,
    user_message: str,
    model_client: ChatCompletionClient,
    state_model_client: ChatCompletionClient | None = None,
    recent_limit: int = 12,
) -> TurnResult:
    prepared = prepare_gm_turn(vault, scenario_id=scenario_id, session_id=session_id, user_message=user_message, recent_limit=recent_limit)
    result = model_client.create_chat_completion(prepared.profile, prepared.messages)
    return finalize_gm_turn(
        vault,
        scenario_id=scenario_id,
        session_id=session_id,
        user_message=user_message,
        assistant_content=result.content,
        prepared=prepared,
        state_model_client=state_model_client,
    )


def run_gm_turn_stream(
    vault: Vault,
    *,
    scenario_id: str,
    session_id: str,
    user_message: str,
    model_client: StreamingChatCompletionClient,
    on_delta: Callable[[str], None],
    state_model_client: ChatCompletionClient | None = None,
    recent_limit: int = 12,
) -> TurnResult:
    prepared = prepare_gm_turn(vault, scenario_id=scenario_id, session_id=session_id, user_message=user_message, recent_limit=recent_limit)
    chunks: list[str] = []
    for chunk in model_client.create_chat_completion_stream(prepared.profile, prepared.messages):
        if not chunk:
            continue
        chunks.append(chunk)
        on_delta(chunk)
    return finalize_gm_turn(
        vault,
        scenario_id=scenario_id,
        session_id=session_id,
        user_message=user_message,
        assistant_content="".join(chunks),
        prepared=prepared,
        state_model_client=state_model_client,
    )


def prepare_gm_turn(
    vault: Vault,
    *,
    scenario_id: str,
    session_id: str,
    user_message: str,
    recent_limit: int = 12,
    recent_log_override: list[dict[str, Any]] | None = None,
) -> TurnPreparation:
    if not isinstance(user_message, str) or not user_message.strip():
        raise TurnLoopError("user_message must be a non-empty string")
    metadata = read_session_metadata(vault, scenario_id, session_id)
    if metadata.get("scenario_id") != scenario_id:
        raise TurnLoopError("Session metadata scenario_id does not match request")

    _require_metadata_string(metadata, "persona_id")
    rp_profile_id = _require_metadata_string(metadata, "rp_profile_id")
    turn = _next_turn(metadata)
    scenario = load_scenario(vault, scenario_id)
    profile = load_profile(vault, rp_profile_id)
    if recent_log_override is not None:
        raw_recent_log = recent_log_override
    else:
        raw_recent_log = read_session_log(vault, scenario_id, session_id)
    prompt = compose_prompt_graph(
        vault,
        scenario_id=scenario_id,
        session_id=session_id,
        user_message=user_message,
        recent_limit=recent_limit,
        recent_log_override=raw_recent_log,
    )
    recent_log = prompt.get("selected_recent_log")
    if not isinstance(recent_log, list):
        recent_log = raw_recent_log[-recent_limit:] if recent_limit else raw_recent_log
    return TurnPreparation(
        metadata=metadata,
        scenario=scenario,
        profile=profile,
        recent_log=recent_log,
        prompt=prompt,
        messages=prompt["messages"],
        turn=turn,
    )


def finalize_gm_turn(
    vault: Vault,
    *,
    scenario_id: str,
    session_id: str,
    user_message: str,
    assistant_content: str,
    prepared: TurnPreparation,
    state_model_client: ChatCompletionClient | None = None,
) -> TurnResult:
    write_latest_session_prompt(
        vault,
        scenario_id,
        session_id,
            latest_prompt_payload(
            scenario_id=scenario_id,
            session_id=session_id,
            turn=prepared.turn,
            profile=prepared.profile,
            messages=prepared.messages,
            rag_results=_prompt_rag_results(prepared.prompt),
            rag_debug=_prompt_rag_debug(prepared.prompt),
            recent_log_selection=_prompt_recent_log_selection(prepared.prompt),
        ),
    )
    segments = parse_image_markers(assistant_content, scenario=prepared.scenario, vault=vault)

    append_session_log(vault, scenario_id, session_id, turn=prepared.turn, role="user", content=user_message)
    append_session_log(vault, scenario_id, session_id, turn=prepared.turn, role="assistant", content=assistant_content)

    postprocess = run_turn_postprocess(
        vault,
        scenario_id=scenario_id,
        session_id=session_id,
        turn=prepared.turn,
        metadata=prepared.metadata,
        scenario_metadata=prepared.scenario.metadata,
        recent_log=prepared.recent_log,
        user_message=user_message,
        assistant_content=assistant_content,
        state_model_client=state_model_client,
    )

    updated_metadata = read_session_metadata(vault, scenario_id, session_id)
    updated_metadata["turn_count"] = prepared.turn
    updated_metadata["updated_at"] = _now_iso()
    write_session_metadata(vault, scenario_id, session_id, updated_metadata)

    return TurnResult(
        session_id=session_id,
        scenario_id=scenario_id,
        turn=prepared.turn,
        assistant_content=assistant_content,
        messages=prepared.messages,
        segments=segments,
        state_updated=postprocess["state_updated"],
        state_update_error=postprocess["state_update_error"],
        memory_updated=postprocess["memory_updated"],
        memory_update_error=postprocess["memory_update_error"],
        memory_files=postprocess["memory_files"],
    )


def finalize_gm_turn_fast(
    vault: Vault,
    *,
    scenario_id: str,
    session_id: str,
    user_message: str,
    assistant_content: str,
    prepared: TurnPreparation,
) -> TurnResult:
    """Fast IO-only finalization: log, segments, metadata. No LLM calls."""
    write_latest_session_prompt(
        vault,
        scenario_id,
        session_id,
            latest_prompt_payload(
            scenario_id=scenario_id,
            session_id=session_id,
            turn=prepared.turn,
            profile=prepared.profile,
            messages=prepared.messages,
            rag_results=_prompt_rag_results(prepared.prompt),
            rag_debug=_prompt_rag_debug(prepared.prompt),
            recent_log_selection=_prompt_recent_log_selection(prepared.prompt),
        ),
    )
    segments = parse_image_markers(assistant_content, scenario=prepared.scenario, vault=vault)
    append_session_log(vault, scenario_id, session_id, turn=prepared.turn, role="user", content=user_message)
    append_session_log(vault, scenario_id, session_id, turn=prepared.turn, role="assistant", content=assistant_content)
    updated_metadata = dict(prepared.metadata)
    updated_metadata["turn_count"] = prepared.turn
    updated_metadata["updated_at"] = _now_iso()
    write_session_metadata(vault, scenario_id, session_id, updated_metadata)
    return TurnResult(
        session_id=session_id,
        scenario_id=scenario_id,
        turn=prepared.turn,
        assistant_content=assistant_content,
        messages=prepared.messages,
        segments=segments,
        state_updated=False,
        state_update_error=None,
        memory_updated=False,
        memory_update_error=None,
        memory_files=[],
    )


def run_gm_post_turn(
    vault: Vault,
    *,
    scenario_id: str,
    session_id: str,
    user_message: str,
    assistant_content: str,
    prepared: TurnPreparation,
    state_model_client: ChatCompletionClient | None,
) -> dict[str, Any]:
    """Slow post-processing: state update and memory summary (LLM calls)."""
    return run_turn_postprocess(
        vault,
        scenario_id=scenario_id,
        session_id=session_id,
        turn=prepared.turn,
        metadata=prepared.metadata,
        scenario_metadata=prepared.scenario.metadata,
        recent_log=prepared.recent_log,
        user_message=user_message,
        assistant_content=assistant_content,
        state_model_client=state_model_client,
    )


def _section(title: str, content: str) -> str:
    stripped = content.strip()
    if not stripped:
        return ""
    return f"## {title}\n{stripped}"


def _scenario_text(scenario: Scenario) -> str:
    parts = [f"ID: {scenario.id}", f"Name: {scenario.name}"]
    if scenario.body.strip():
        parts.append(scenario.body.strip())
    return "\n".join(parts)


def _persona_text(persona: Persona) -> str:
    parts = [f"ID: {persona.id}", f"Name: {persona.name}"]
    if persona.body.strip():
        parts.append(persona.body.strip())
    return "\n".join(parts)


def _state_text(state: dict[str, Any]) -> str:
    return json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True)


def _image_policy_text(scenario: Scenario) -> str:
    image_enabled = scenario.metadata.get("image_enabled")
    image_mode = scenario.metadata.get("image_mode")
    if image_enabled is not True:
        return ""
    if scenario.image_policy.strip():
        return scenario.image_policy
    return json.dumps(
        {"image_enabled": image_enabled, "image_mode": image_mode},
        ensure_ascii=False,
        sort_keys=True,
    )


def _require_metadata_string(metadata: dict[str, Any], field: str) -> str:
    value = metadata.get(field)
    if not isinstance(value, str) or not value.strip():
        raise TurnLoopError(f"Session metadata field is missing or invalid: {field}")
    return value


def _prompt_rag_results(prompt: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for expansion in prompt.get("expansions", []):
        if not isinstance(expansion, dict) or expansion.get("type") != "rag":
            continue
        for result in expansion.get("results", []):
            if not isinstance(result, dict):
                continue
            source_path = result.get("source_path")
            if not isinstance(source_path, str) or source_path in seen:
                continue
            seen.add(source_path)
            results.append(
                {
                    "source_path": source_path,
                    "type": result.get("type"),
                    "title": result.get("title"),
                    "score": result.get("score"),
                    "content": result.get("content"),
                    "metadata": result.get("metadata") if isinstance(result.get("metadata"), dict) else {},
                    "matched_terms": result.get("matched_terms") if isinstance(result.get("matched_terms"), list) else [],
                }
            )
    return results


def _prompt_rag_debug(prompt: dict[str, Any]) -> list[dict[str, Any]]:
    debug: list[dict[str, Any]] = []
    for expansion in prompt.get("expansions", []):
        if not isinstance(expansion, dict) or expansion.get("type") != "rag":
            continue
        debug.append(
            {
                "node_id": expansion.get("node_id"),
                "title": expansion.get("title"),
                "included": expansion.get("included") is True,
                "skipped_reason": expansion.get("skipped_reason") or "",
                "query": expansion.get("query") if isinstance(expansion.get("query"), str) else "",
                "sources": expansion.get("sources") if isinstance(expansion.get("sources"), list) else [],
                "limit": expansion.get("limit"),
                "retrieved_count": expansion.get("retrieved_count", 0),
                "included_count": expansion.get("included_count", len(expansion.get("results", []))),
                "token_budget": expansion.get("token_budget"),
            }
        )
    return debug


def _prompt_recent_log_selection(prompt: dict[str, Any]) -> dict[str, Any]:
    value = prompt.get("recent_log_selection")
    return value if isinstance(value, dict) else {}


def _next_turn(metadata: dict[str, Any]) -> int:
    current = metadata.get("turn_count", 0)
    if not isinstance(current, int) or current < 0:
        raise TurnLoopError("Session metadata turn_count must be a non-negative integer")
    return current + 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

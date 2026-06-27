from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Protocol

from app.loaders import ModelProfile, Scenario, load_profile, load_scenario
from app.images import Segment, parse_image_markers
from app.model_client import ChatCompletionResult
from app.prompt_preview import compose_prompt_graph
from app.reasoning import sanitize_log_entries, strip_reasoning_blocks as _strip_reasoning_blocks
from app.state_session import (
    append_session_log,
    read_session_log,
    read_session_metadata,
    update_session_log_entry,
    write_latest_session_prompt,
    write_session_metadata,
)
from app.turn_postprocess import run_turn_postprocess
from app.turn_prompt_payload import latest_prompt_payload
from app.rag_types import document_key_from_parts
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
    response_duration_ms: int | None = None
    timings_ms: dict[str, int] | None = None


@dataclass(frozen=True)
class TurnPreparation:
    metadata: dict[str, Any]
    scenario: Scenario
    profile: ModelProfile
    recent_log: list[dict[str, Any]]
    prompt: dict[str, Any]
    messages: list[dict[str, str]]
    turn: int
    timings_ms: dict[str, int]


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
    started = time.perf_counter()
    result = model_client.create_chat_completion(prepared.profile, prepared.messages)
    response_duration_ms = _duration_ms(started)
    timings_ms = _turn_timings(prepared, rp_model_ms=response_duration_ms)
    return finalize_gm_turn(
        vault,
        scenario_id=scenario_id,
        session_id=session_id,
        user_message=user_message,
        assistant_content=result.content,
        prepared=prepared,
        state_model_client=state_model_client,
        response_duration_ms=response_duration_ms,
        timings_ms=timings_ms,
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
    started = time.perf_counter()
    for chunk in model_client.create_chat_completion_stream(prepared.profile, prepared.messages):
        if not chunk:
            continue
        chunks.append(chunk)
        on_delta(chunk)
    response_duration_ms = _duration_ms(started)
    timings_ms = _turn_timings(prepared, rp_model_ms=response_duration_ms)
    return finalize_gm_turn(
        vault,
        scenario_id=scenario_id,
        session_id=session_id,
        user_message=user_message,
        assistant_content="".join(chunks),
        prepared=prepared,
        state_model_client=state_model_client,
        response_duration_ms=response_duration_ms,
        timings_ms=timings_ms,
    )


def prepare_gm_turn(
    vault: Vault,
    *,
    scenario_id: str,
    session_id: str,
    user_message: str,
    recent_limit: int = 12,
    recent_log_override: list[dict[str, Any]] | None = None,
    state_override: dict[str, Any] | None = None,
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
        raw_recent_log = sanitize_log_entries(recent_log_override)
    else:
        raw_recent_log = sanitize_log_entries(read_session_log(vault, scenario_id, session_id))
    prompt = compose_prompt_graph(
        vault,
        scenario_id=scenario_id,
        session_id=session_id,
        user_message=user_message,
        recent_limit=recent_limit,
        recent_log_override=raw_recent_log,
        state_override=state_override,
    )
    timings_ms = _prompt_timings(prompt)
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
        timings_ms=timings_ms,
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
    response_duration_ms: int | None = None,
    timings_ms: dict[str, int] | None = None,
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
    postprocess_content = _strip_reasoning_blocks(assistant_content)

    append_session_log(vault, scenario_id, session_id, turn=prepared.turn, role="user", content=user_message)
    assistant_timings = _turn_timings(prepared, rp_model_ms=response_duration_ms, timings_ms=timings_ms)
    assistant_extra = _assistant_timing_extra(
        response_duration_ms=response_duration_ms,
        timings_ms=assistant_timings,
    )
    append_session_log(
        vault,
        scenario_id,
        session_id,
        turn=prepared.turn,
        role="assistant",
        content=postprocess_content,
        extra=assistant_extra,
    )

    postprocess = run_turn_postprocess(
        vault,
        scenario_id=scenario_id,
        session_id=session_id,
        turn=prepared.turn,
        metadata=prepared.metadata,
        scenario_metadata=prepared.scenario.metadata,
        recent_log=prepared.recent_log,
        user_message=user_message,
        assistant_content=postprocess_content,
        state_model_client=state_model_client,
    )
    result_timings = _merge_timings(assistant_timings, postprocess.get("timings_ms"))
    _merge_assistant_timings(vault, scenario_id, session_id, prepared.turn, result_timings)

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
        response_duration_ms=response_duration_ms,
        timings_ms=result_timings,
    )


def finalize_gm_turn_fast(
    vault: Vault,
    *,
    scenario_id: str,
    session_id: str,
    user_message: str,
    assistant_content: str,
    prepared: TurnPreparation,
    response_duration_ms: int | None = None,
    timings_ms: dict[str, int] | None = None,
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
    log_content = _strip_reasoning_blocks(assistant_content)
    append_session_log(vault, scenario_id, session_id, turn=prepared.turn, role="user", content=user_message)
    assistant_timings = _turn_timings(prepared, rp_model_ms=response_duration_ms, timings_ms=timings_ms)
    assistant_extra = _assistant_timing_extra(
        response_duration_ms=response_duration_ms,
        timings_ms=assistant_timings,
    )
    append_session_log(
        vault,
        scenario_id,
        session_id,
        turn=prepared.turn,
        role="assistant",
        content=log_content,
        extra=assistant_extra,
    )
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
        response_duration_ms=response_duration_ms,
        timings_ms=assistant_timings,
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
    postprocess_content = _strip_reasoning_blocks(assistant_content)
    postprocess = run_turn_postprocess(
        vault,
        scenario_id=scenario_id,
        session_id=session_id,
        turn=prepared.turn,
        metadata=prepared.metadata,
        scenario_metadata=prepared.scenario.metadata,
        recent_log=prepared.recent_log,
        user_message=user_message,
        assistant_content=postprocess_content,
        state_model_client=state_model_client,
    )
    _merge_assistant_timings(vault, scenario_id, session_id, prepared.turn, postprocess.get("timings_ms"))
    return postprocess


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
            chunk_id = result.get("chunk_id")
            if not isinstance(source_path, str):
                continue
            result_key = document_key_from_parts(source_path, chunk_id if isinstance(chunk_id, str) else None)
            if result_key in seen:
                continue
            seen.add(result_key)
            results.append(
                {
                    "source_path": source_path,
                    "chunk_id": chunk_id if isinstance(chunk_id, str) and chunk_id else None,
                    "heading_path": result.get("heading_path") if isinstance(result.get("heading_path"), list) else [],
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
                "keyword_token_budget": expansion.get("keyword_token_budget"),
                "token_budgets": expansion.get("token_budgets") if isinstance(expansion.get("token_budgets"), dict) else {},
                "duration_ms": expansion.get("duration_ms") if isinstance(expansion.get("duration_ms"), int) else None,
            }
        )
    return debug


def _prompt_recent_log_selection(prompt: dict[str, Any]) -> dict[str, Any]:
    value = prompt.get("recent_log_selection")
    return value if isinstance(value, dict) else {}


def _prompt_timings(prompt: dict[str, Any]) -> dict[str, int]:
    rag_duration_ms = 0
    has_rag_duration = False
    for expansion in prompt.get("expansions", []):
        if not isinstance(expansion, dict) or expansion.get("type") != "rag":
            continue
        duration = expansion.get("duration_ms")
        if isinstance(duration, int) and not isinstance(duration, bool) and duration >= 0:
            rag_duration_ms += duration
            has_rag_duration = True
    return {"rag_search_ms": rag_duration_ms} if has_rag_duration else {}


def _next_turn(metadata: dict[str, Any]) -> int:
    current = metadata.get("turn_count", 0)
    if not isinstance(current, int) or current < 0:
        raise TurnLoopError("Session metadata turn_count must be a non-negative integer")
    return current + 1


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _duration_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


def _turn_timings(
    prepared: TurnPreparation,
    *,
    rp_model_ms: int | None = None,
    timings_ms: dict[str, int] | None = None,
) -> dict[str, int]:
    timings = _merge_timings(prepared.timings_ms, timings_ms)
    if rp_model_ms is not None:
        timings["rp_model_ms"] = rp_model_ms
    return timings


def _assistant_timing_extra(
    *,
    response_duration_ms: int | None,
    timings_ms: dict[str, int] | None,
) -> dict[str, Any] | None:
    extra: dict[str, Any] = {}
    if response_duration_ms is not None:
        extra["response_duration_ms"] = response_duration_ms
    normalized = _normalize_timings(timings_ms)
    if normalized:
        extra["timings_ms"] = normalized
    return extra or None


def _merge_assistant_timings(
    vault: Vault,
    scenario_id: str,
    session_id: str,
    turn: int,
    timings_ms: Any,
) -> None:
    timings = _normalize_timings(timings_ms)
    if not timings:
        return
    existing: dict[str, int] = {}
    for entry in read_session_log(vault, scenario_id, session_id):
        if entry.get("turn") == turn and entry.get("role") == "assistant":
            existing = _normalize_timings(entry.get("timings_ms"))
            break
    merged = _merge_timings(existing, timings)
    if merged:
        update_session_log_entry(vault, scenario_id, session_id, turn, "assistant", {"timings_ms": merged})


def _merge_timings(*items: Any) -> dict[str, int]:
    merged: dict[str, int] = {}
    for item in items:
        merged.update(_normalize_timings(item))
    return merged


def _normalize_timings(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    timings: dict[str, int] = {}
    for key, raw in value.items():
        if not isinstance(key, str):
            continue
        if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
            continue
        timings[key] = raw
    return timings

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Iterable, cast
from app.api_validation import ApiBadRequest
from app.images import parse_image_markers
from app.model_client import OpenAICompatibleClient
from app.postprocess_jobs import read_postprocess_job, start_postprocess_job
from app.state_session import (
    append_session_log,
    read_session_candidate_state,
    read_session_log,
    read_session_metadata,
    read_session_state,
    read_session_state_snapshot,
    write_latest_session_prompt,
    write_session_candidate_state,
    write_session_metadata,
    write_session_state,
    write_session_state_snapshot,
    update_session_log_entry,
    delete_session_log_entry,
    delete_session_log_from_turn,
)
from app.state_updater import run_state_update
from app.turn_loop import (
    ChatCompletionClient,
    StreamingChatCompletionClient,
    _prompt_rag_debug,
    _prompt_rag_results,
    _prompt_recent_log_selection,
    _now_iso,
    finalize_gm_turn_fast,
    prepare_gm_turn,
    run_gm_turn,
)
from app.reasoning import remove_reasoning_blocks as _remove_reasoning_blocks
from app.reasoning import strip_reasoning_blocks as _strip_reasoning_blocks
from app.turn_prompt_payload import latest_prompt_payload
from app.turn_payloads import segment_payload, turn_result_payload
from app.turn_jobs import find_active_turn_job, read_turn_job, start_turn_job
from app.vault import Vault, VaultError
from app.api.common import ApiResponse, ApiStreamResponse, _duration_ms, _json_response, _sse_event


@dataclass(frozen=True)
class _RegenerateTargetContext:
    target_entry: dict[str, Any]
    user_message: str
    recent_log: list[dict[str, Any]]
    state_before_turn: dict[str, Any]
    state_source: dict[str, Any]


def _turn_response(
    vault: Vault,
    scenario_id: str,
    session_id: str,
    payload: dict[str, Any],
    *,
    model_client: ChatCompletionClient | None,
    state_model_client: ChatCompletionClient | None,
) -> ApiResponse:
    user_message = payload.get("user_message")
    if not isinstance(user_message, str) or not user_message.strip():
        raise ApiBadRequest("user_message must be a non-empty string")
    stream = payload.get("stream", False)
    if not isinstance(stream, bool):
        raise ApiBadRequest("stream must be a boolean")
    async_requested = payload.get("async", False)
    if not isinstance(async_requested, bool):
        raise ApiBadRequest("async must be a boolean")
    defer_postprocess = payload.get("defer_postprocess", False)
    if not isinstance(defer_postprocess, bool):
        raise ApiBadRequest("defer_postprocess must be a boolean")
    if stream and async_requested:
        raise ApiBadRequest("stream and async cannot both be true")
    if async_requested:
        active = find_active_turn_job(vault, scenario_id, session_id)
        if active is not None:
            return _json_response({"turn_job": _public_turn_job(active)}, status=409)
        client = model_client or OpenAICompatibleClient()
        state_client = state_model_client if state_model_client is not None else client
        turn_job = start_turn_job(
            vault,
            scenario_id=scenario_id,
            session_id=session_id,
            user_message=user_message,
            model_client=client,
            state_model_client=state_client,
            defer_postprocess=defer_postprocess,
        )
        return _json_response({"turn_job": _public_turn_job(turn_job)}, status=202)
    if stream:
        if not hasattr(model_client or OpenAICompatibleClient, "create_chat_completion_stream"):
            return _json_response(
                {
                    "error": "not_implemented",
                    "message": "The configured model client does not support streaming. Set stream to false.",
                },
                status=501,
            )
        client = cast(StreamingChatCompletionClient, model_client or OpenAICompatibleClient())
        state_client = state_model_client if state_model_client is not None else client
        return _turn_stream_response(
            vault,
            scenario_id=scenario_id,
            session_id=session_id,
            user_message=user_message,
            model_client=client,
            state_model_client=state_client,
        )

    client = model_client or OpenAICompatibleClient()
    state_client = state_model_client if state_model_client is not None else client
    if defer_postprocess:
        prepared = prepare_gm_turn(
            vault,
            scenario_id=scenario_id,
            session_id=session_id,
            user_message=user_message,
        )
        started = time.perf_counter()
        completion = client.create_chat_completion(prepared.profile, prepared.messages)
        response_duration_ms = _duration_ms(started)
        timings_ms = _response_timings(prepared, response_duration_ms)
        result = finalize_gm_turn_fast(
            vault,
            scenario_id=scenario_id,
            session_id=session_id,
            user_message=user_message,
            assistant_content=completion.content,
            prepared=prepared,
            response_duration_ms=response_duration_ms,
            timings_ms=timings_ms,
        )
        postprocess_job = start_postprocess_job(
            vault,
            scenario_id=scenario_id,
            session_id=session_id,
            user_message=user_message,
            assistant_content=completion.content,
            prepared=prepared,
            state_model_client=state_client,
        )
        return _json_response(
            {
                "turn": turn_result_payload(result),
                "postprocess_job": _public_postprocess_job(postprocess_job),
            }
        )
    result = run_gm_turn(
        vault,
        scenario_id=scenario_id,
        session_id=session_id,
        user_message=user_message,
        model_client=client,
        state_model_client=state_client,
    )
    return _json_response({"turn": turn_result_payload(result)})


def _turn_job_response(vault: Vault, scenario_id: str, session_id: str, turn_id: str) -> dict[str, Any]:
    read_session_metadata(vault, scenario_id, session_id)
    return {"turn_job": _public_turn_job(read_turn_job(vault, scenario_id, session_id, turn_id))}


def _postprocess_job_response(vault: Vault, scenario_id: str, session_id: str, job_id: str) -> dict[str, Any]:
    read_session_metadata(vault, scenario_id, session_id)
    return {"postprocess_job": _public_postprocess_job(read_postprocess_job(vault, scenario_id, session_id, job_id))}


def _public_turn_job(turn_job: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "turn_id": turn_job.get("turn_id"),
        "scenario_id": turn_job.get("scenario_id"),
        "session_id": turn_job.get("session_id"),
        "turn": turn_job.get("turn"),
        "status": turn_job.get("status"),
        "created_at": turn_job.get("created_at"),
        "updated_at": turn_job.get("updated_at"),
        "started_at": turn_job.get("started_at"),
        "completed_at": turn_job.get("completed_at"),
        "error": turn_job.get("error"),
        "result": turn_job.get("result"),
    }
    return {key: value for key, value in payload.items() if value is not None}


def _public_postprocess_job(job: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "job_id": job.get("job_id"),
        "scenario_id": job.get("scenario_id"),
        "session_id": job.get("session_id"),
        "turn": job.get("turn"),
        "status": job.get("status"),
        "created_at": job.get("created_at"),
        "updated_at": job.get("updated_at"),
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
        "error": job.get("error"),
        "result": job.get("result"),
    }
    return {key: value for key, value in payload.items() if value is not None}


def _turn_stream_response(
    vault: Vault,
    *,
    scenario_id: str,
    session_id: str,
    user_message: str,
    model_client: StreamingChatCompletionClient,
    state_model_client: ChatCompletionClient | None,
) -> ApiStreamResponse:
    def events() -> Iterable[bytes]:
        yield _sse_event("start", {"scenario_id": scenario_id, "session_id": session_id})
        try:
            prepared = prepare_gm_turn(
                vault,
                scenario_id=scenario_id,
                session_id=session_id,
                user_message=user_message,
            )
            chunks: list[str] = []
            started = time.perf_counter()
            for delta in model_client.create_chat_completion_stream(prepared.profile, prepared.messages):
                if not delta:
                    continue
                chunks.append(delta)
                yield _sse_event("delta", {"delta": delta})
            assistant_content = "".join(chunks)
            response_duration_ms = _duration_ms(started)
            timings_ms = _response_timings(prepared, response_duration_ms)
            result = finalize_gm_turn_fast(
                vault,
                scenario_id=scenario_id,
                session_id=session_id,
                user_message=user_message,
                assistant_content=assistant_content,
                prepared=prepared,
                response_duration_ms=response_duration_ms,
                timings_ms=timings_ms,
            )
            yield _sse_event("final", {"turn": turn_result_payload(result)})
            postprocess_job = start_postprocess_job(
                vault,
                scenario_id=scenario_id,
                session_id=session_id,
                user_message=user_message,
                assistant_content=assistant_content,
                prepared=prepared,
                state_model_client=state_model_client,
            )
            yield _sse_event("post_turn", {"postprocess_job": _public_postprocess_job(postprocess_job)})
        except Exception as exc:
            yield _sse_event("error", {"error": type(exc).__name__, "message": str(exc)})

    return ApiStreamResponse(status=200, content_type="text/event-stream; charset=utf-8", events=events())


def _update_session_message_response(vault: Vault, scenario_id: str, session_id: str, turn: int, role: str, payload: dict[str, Any]) -> dict[str, Any]:
    content = payload.get("content")
    if not isinstance(content, str):
        raise ApiBadRequest("content must be a string")

    entries = read_session_log(vault, scenario_id, session_id)
    target_entry = None
    for entry in entries:
        if entry.get("turn") == turn and entry.get("role") == role:
            target_entry = entry
            break

    if not target_entry:
        raise ApiBadRequest("Message not found")

    updates = {}
    if "candidates" in target_entry and role == "assistant":
        candidates = list(target_entry["candidates"])
        active = target_entry.get("active_candidate_index", 0)
        if 0 <= active < len(candidates):
            candidates[active] = content
        else:
            candidates.append(content)
            active = len(candidates) - 1
        updates["candidates"] = candidates
        updates["active_candidate_index"] = active
    updates["content"] = content

    updated = update_session_log_entry(vault, scenario_id, session_id, turn, role, updates)
    return {"scenario_id": scenario_id, "session_id": session_id, "turn": turn, "role": role, "updated": True, "entry": updated}


def _update_session_message_candidate_response(vault: Vault, scenario_id: str, session_id: str, turn: int, payload: dict[str, Any]) -> dict[str, Any]:
    index = payload.get("index", payload.get("candidate_index"))
    if not isinstance(index, int) or index < 0:
        raise ApiBadRequest("index must be a non-negative integer")

    entries = read_session_log(vault, scenario_id, session_id)
    target_entry = None
    for entry in entries:
        if entry.get("turn") == turn and entry.get("role") == "assistant":
            target_entry = entry
            break

    if not target_entry:
        raise ApiBadRequest("Assistant message not found")

    raw_candidates = target_entry.get("candidates", [])
    candidates = [
        _strip_reasoning_blocks(candidate) if isinstance(candidate, str) else ""
        for candidate in (raw_candidates if isinstance(raw_candidates, list) else [])
    ]
    if not candidates:
        if index == 0:
            return {"scenario_id": scenario_id, "session_id": session_id, "turn": turn, "role": "assistant", "updated": False, "entry": target_entry}
        raise ApiBadRequest("No candidates available")

    if index >= len(candidates):
        raise ApiBadRequest(f"Candidate index out of bounds (max {len(candidates) - 1})")

    state_restored = False
    state_restore_reason = ""
    candidate_states = target_entry.get("candidate_states")
    if isinstance(candidate_states, list) and index < len(candidate_states):
        state_info = candidate_states[index]
        if isinstance(state_info, dict) and state_info.get("state_updated") is True:
            if _latest_assistant_turn(entries) == turn:
                try:
                    state = read_session_candidate_state(vault, scenario_id, session_id, turn, index)
                    write_session_state(vault, scenario_id, session_id, state)
                    write_session_state_snapshot(vault, scenario_id, session_id, turn, state)
                    state_restored = True
                except Exception as exc:
                    state_restore_reason = f"candidate_state_unavailable:{type(exc).__name__}"
            else:
                state_restore_reason = "not_latest_turn"
        else:
            state_restore_reason = "candidate_state_unavailable"
    else:
        state_restore_reason = "candidate_state_unavailable"

    updates = {
        "active_candidate_index": index,
        "content": candidates[index],
        "candidates": candidates,
    }
    candidate_durations = target_entry.get("candidate_response_durations_ms")
    if isinstance(candidate_durations, list):
        updates["candidate_response_durations_ms"] = candidate_durations
        if index < len(candidate_durations) and isinstance(candidate_durations[index], int):
            updates["response_duration_ms"] = candidate_durations[index]
    updated = update_session_log_entry(vault, scenario_id, session_id, turn, "assistant", updates)
    return {
        "scenario_id": scenario_id,
        "session_id": session_id,
        "turn": turn,
        "role": "assistant",
        "updated": True,
        "entry": updated,
        "state_restored": state_restored,
        "state_restore_reason": state_restore_reason,
    }


def _delete_session_message_response(vault: Vault, scenario_id: str, session_id: str, turn: int, role: str, query: dict[str, list[str]]) -> dict[str, Any]:
    rewind = query.get("rewind", [""])[0].lower() == "true"
    if rewind:
        deleted = delete_session_log_from_turn(vault, scenario_id, session_id, turn)
    else:
        deleted = delete_session_log_entry(vault, scenario_id, session_id, turn, role)

    if not deleted:
        raise ApiBadRequest("Message not found or nothing deleted")

    return {"scenario_id": scenario_id, "session_id": session_id, "turn": turn, "role": role, "deleted": True, "rewind": rewind}


def _regenerate_session_message_response(
    vault: Vault,
    scenario_id: str,
    session_id: str,
    turn: int,
    payload: dict[str, Any],
    *,
    model_client: ChatCompletionClient | None = None,
    state_model_client: ChatCompletionClient | None = None,
) -> ApiResponse | ApiStreamResponse:
    if model_client is None:
        model_client = OpenAICompatibleClient()
    state_client = state_model_client if state_model_client is not None else model_client

    stream = payload.get("stream", False)
    if not isinstance(stream, bool):
        raise ApiBadRequest("stream must be a boolean")

    entries = read_session_log(vault, scenario_id, session_id)
    target = _regenerate_target_context(vault, scenario_id, session_id, turn, entries)

    prepared = prepare_gm_turn(
        vault,
        scenario_id=scenario_id,
        session_id=session_id,
        user_message=target.user_message,
        recent_limit=12,
        recent_log_override=target.recent_log,
        state_override=target.state_before_turn,
    )
    _write_regenerate_latest_prompt(vault, scenario_id, session_id, turn, prepared, target.state_source)

    def _on_success(content: str, token_usage: dict[str, int], response_duration_ms: int) -> bytes:
        timings_ms = _response_timings(prepared, response_duration_ms)
        updated, state_info, state_restored = _append_regenerated_candidate(
            vault,
            scenario_id=scenario_id,
            session_id=session_id,
            turn=turn,
            target_entry=target.target_entry,
            entries=entries,
            metadata=prepared.metadata,
            base_state=target.state_before_turn,
            recent_log=prepared.recent_log,
            user_message=target.user_message,
            assistant_content=content,
            state_model_client=state_client,
            response_duration_ms=response_duration_ms,
            timings_ms=timings_ms,
        )

        return json.dumps(
            {
                "scenario_id": scenario_id,
                "session_id": session_id,
                "turn": turn,
                "role": "assistant",
                "entry": updated,
                "token_usage": token_usage,
                "response_duration_ms": response_duration_ms,
                "timings_ms": updated.get("timings_ms"),
                "state_source": target.state_source,
                "state_candidate": state_info,
                "state_restored": state_restored,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

    if stream and hasattr(model_client, "create_chat_completion_stream"):
        def _generate() -> Iterable[bytes]:
            chunks: list[str] = []
            try:
                started = time.perf_counter()
                for chunk in model_client.create_chat_completion_stream(prepared.profile, prepared.messages):
                    if not chunk:
                        continue
                    chunks.append(chunk)
                    yield _sse_event("delta", {"delta": chunk})
                final_content = "".join(chunks)
                yield _sse_event("final", json.loads(_on_success(final_content, {}, _duration_ms(started))))
            except Exception as exc:
                yield _sse_event("error", {"error": type(exc).__name__, "message": str(exc)})

        return ApiStreamResponse(status=200, content_type="text/event-stream; charset=utf-8", events=_generate())
    else:
        started = time.perf_counter()
        result = model_client.create_chat_completion(prepared.profile, prepared.messages)
        response_duration_ms = _duration_ms(started)
        return ApiResponse(
            status=200,
            content_type="application/json; charset=utf-8",
            body=_on_success(result.content, getattr(result, "token_usage", {}), response_duration_ms),
        )


def _state_before_turn(vault: Vault, scenario_id: str, session_id: str, turn: int) -> tuple[dict[str, Any], dict[str, Any]]:
    previous_turn = max(0, turn - 1)
    try:
        return read_session_state_snapshot(vault, scenario_id, session_id, previous_turn), {
            "source": "snapshot",
            "turn": previous_turn,
        }
    except VaultError:
        return read_session_state(vault, scenario_id, session_id), {
            "source": "current_state_fallback",
            "turn": previous_turn,
        }


def _regenerate_target_context(
    vault: Vault,
    scenario_id: str,
    session_id: str,
    turn: int,
    entries: list[dict[str, Any]],
) -> _RegenerateTargetContext:
    target_entry = None
    user_message = ""
    for entry in entries:
        if entry.get("turn") == turn and entry.get("role") == "user":
            user_message = entry.get("content", "")
        if entry.get("turn") == turn and entry.get("role") == "assistant":
            target_entry = entry
            break
    if not target_entry:
        raise ApiBadRequest("Assistant message not found for the specified turn")
    state_before_turn, state_source = _state_before_turn(vault, scenario_id, session_id, turn)
    return _RegenerateTargetContext(
        target_entry=target_entry,
        user_message=user_message,
        recent_log=_pre_turn_recent_log(entries, turn),
        state_before_turn=state_before_turn,
        state_source=state_source,
    )


def _pre_turn_recent_log(entries: list[dict[str, Any]], turn: int) -> list[dict[str, Any]]:
    recent_log: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry.get("turn"), int):
            continue
        if entry["turn"] >= turn:
            continue
        recent_log.append(entry)
    return recent_log


def _write_regenerate_latest_prompt(
    vault: Vault,
    scenario_id: str,
    session_id: str,
    turn: int,
    prepared: Any,
    state_source: dict[str, Any],
) -> None:
    write_latest_session_prompt(
        vault,
        scenario_id,
        session_id,
        latest_prompt_payload(
            scenario_id=scenario_id,
            session_id=session_id,
            turn=turn,
            profile=prepared.profile,
            messages=prepared.messages,
            rag_results=_prompt_rag_results(prepared.prompt),
            rag_debug=_prompt_rag_debug(prepared.prompt),
            recent_log_selection=_prompt_recent_log_selection(prepared.prompt),
        )
        | {"state_source": state_source},
    )


def _append_regenerated_candidate(
    vault: Vault,
    *,
    scenario_id: str,
    session_id: str,
    turn: int,
    target_entry: dict[str, Any],
    entries: list[dict[str, Any]],
    metadata: dict[str, Any],
    base_state: dict[str, Any],
    recent_log: list[dict[str, Any]],
    user_message: str,
    assistant_content: str,
    state_model_client: ChatCompletionClient | None,
    response_duration_ms: int,
    timings_ms: dict[str, int],
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    assistant_content = _strip_reasoning_blocks(assistant_content)
    raw_candidates = target_entry.get("candidates", [])
    candidates = [
        _strip_reasoning_blocks(candidate) if isinstance(candidate, str) else ""
        for candidate in (raw_candidates if isinstance(raw_candidates, list) else [])
    ]
    if not candidates:
        original_content = target_entry.get("content", "")
        candidates.append(_strip_reasoning_blocks(original_content) if isinstance(original_content, str) else "")
    candidate_states = _candidate_states_for_existing_candidates(
        vault,
        scenario_id=scenario_id,
        session_id=session_id,
        turn=turn,
        target_entry=target_entry,
        candidate_count=len(candidates),
    )
    candidates.append(assistant_content)
    active_index = len(candidates) - 1
    candidate_durations = _candidate_response_durations(target_entry, len(candidates) - 1)
    candidate_durations.append(response_duration_ms)
    state_info = _state_info_for_regenerated_candidate(
        vault,
        scenario_id=scenario_id,
        session_id=session_id,
        turn=turn,
        candidate_index=active_index,
        metadata=metadata,
        base_state=base_state,
        recent_log=recent_log,
        user_message=user_message,
        assistant_content=assistant_content,
        state_model_client=state_model_client,
    )
    state_timings = state_info.get("timings_ms")
    if isinstance(state_timings, dict):
        timings_ms = _merge_timings(timings_ms, state_timings)
    candidate_states.append(state_info)
    state_restored = _restore_candidate_state_if_latest(
        vault,
        scenario_id=scenario_id,
        session_id=session_id,
        turn=turn,
        candidate_index=active_index,
        entries=entries,
        state_info=state_info,
    )
    updated = update_session_log_entry(
        vault,
        scenario_id,
        session_id,
        turn,
        "assistant",
        {
            "content": assistant_content,
            "candidates": candidates,
            "active_candidate_index": active_index,
            "candidate_states": candidate_states,
            "candidate_response_durations_ms": candidate_durations,
            "response_duration_ms": response_duration_ms,
            "timings_ms": timings_ms,
        },
    )
    return updated, state_info, state_restored


def _candidate_response_durations(target_entry: dict[str, Any], candidate_count: int) -> list[int | None]:
    existing = target_entry.get("candidate_response_durations_ms")
    if isinstance(existing, list):
        durations = [item if isinstance(item, int) and item >= 0 else None for item in existing[:candidate_count]]
    else:
        duration = target_entry.get("response_duration_ms")
        durations = [duration if isinstance(duration, int) and duration >= 0 else None] if candidate_count else []
    while len(durations) < candidate_count:
        durations.append(None)
    return durations


def _candidate_states_for_existing_candidates(
    vault: Vault,
    *,
    scenario_id: str,
    session_id: str,
    turn: int,
    target_entry: dict[str, Any],
    candidate_count: int,
) -> list[dict[str, Any]]:
    existing = target_entry.get("candidate_states")
    if isinstance(existing, list):
        states = [item if isinstance(item, dict) else {"state_updated": False} for item in existing[:candidate_count]]
    else:
        states = []
    if not states and candidate_count > 0:
        state, source = _state_after_turn(vault, scenario_id, session_id, turn)
        path = write_session_candidate_state(vault, scenario_id, session_id, turn, 0, state)
        states.append({"state_updated": True, "state_path": path, "source": source})
    while len(states) < candidate_count:
        states.append({"state_updated": False})
    return states


def _state_after_turn(vault: Vault, scenario_id: str, session_id: str, turn: int) -> tuple[dict[str, Any], str]:
    try:
        return read_session_state_snapshot(vault, scenario_id, session_id, turn), "snapshot"
    except VaultError:
        return read_session_state(vault, scenario_id, session_id), "current_state_fallback"


def _state_info_for_regenerated_candidate(
    vault: Vault,
    *,
    scenario_id: str,
    session_id: str,
    turn: int,
    candidate_index: int,
    metadata: dict[str, Any],
    base_state: dict[str, Any],
    recent_log: list[dict[str, Any]],
    user_message: str,
    assistant_content: str,
    state_model_client: ChatCompletionClient | None,
) -> dict[str, Any]:
    summary_profile_id = metadata.get("summary_profile_id")
    if state_model_client is None or not isinstance(summary_profile_id, str) or not summary_profile_id.strip():
        return {"state_updated": False, "state_update_error": None}
    started = time.perf_counter()
    try:
        result = run_state_update(
            vault,
            scenario_id=scenario_id,
            session_id=session_id,
            turn=turn,
            profile_id=summary_profile_id,
            user_message=user_message,
            gm_response=assistant_content,
            model_client=state_model_client,
            recent_context=recent_log,
            current_state_override=base_state,
            persist=False,
        )
        path = write_session_candidate_state(vault, scenario_id, session_id, turn, candidate_index, result.updated_state)
        return {
            "state_updated": True,
            "state_path": path,
            "state_update_error": None,
            "timings_ms": {"state_model_ms": _duration_ms(started)},
        }
    except Exception as exc:
        return {
            "state_updated": False,
            "state_update_error": f"{type(exc).__name__}: {exc}",
            "timings_ms": {"state_model_ms": _duration_ms(started)},
        }


def _restore_candidate_state_if_latest(
    vault: Vault,
    *,
    scenario_id: str,
    session_id: str,
    turn: int,
    candidate_index: int,
    entries: list[dict[str, Any]],
    state_info: dict[str, Any],
) -> bool:
    if state_info.get("state_updated") is not True:
        return False
    if _latest_assistant_turn(entries) != turn:
        return False
    state = read_session_candidate_state(vault, scenario_id, session_id, turn, candidate_index)
    write_session_state(vault, scenario_id, session_id, state)
    write_session_state_snapshot(vault, scenario_id, session_id, turn, state)
    return True


def _latest_assistant_turn(entries: list[dict[str, Any]]) -> int | None:
    turns = [entry.get("turn") for entry in entries if entry.get("role") == "assistant" and isinstance(entry.get("turn"), int)]
    return max(turns) if turns else None


def _continue_session_message_response(
    vault: Vault,
    scenario_id: str,
    session_id: str,
    turn: int,
    payload: dict[str, Any],
    *,
    model_client: ChatCompletionClient | None = None,
) -> ApiResponse | ApiStreamResponse:
    if model_client is None:
        model_client = OpenAICompatibleClient()

    stream = payload.get("stream", False)
    if not isinstance(stream, bool):
        raise ApiBadRequest("stream must be a boolean")

    entries = read_session_log(vault, scenario_id, session_id)
    target_entry = None
    latest_assistant_turn = None
    for entry in entries:
        if entry.get("role") != "assistant" or not isinstance(entry.get("turn"), int):
            continue
        latest_assistant_turn = entry["turn"] if latest_assistant_turn is None else max(latest_assistant_turn, entry["turn"])
        if entry.get("turn") == turn:
            target_entry = entry

    if not target_entry:
        raise ApiBadRequest("Assistant message not found for the specified turn")
    if latest_assistant_turn != turn:
        raise ApiBadRequest("Only the latest assistant message can be continued")

    recent_log_override = [
        entry
        for entry in entries
        if isinstance(entry.get("turn"), int) and entry["turn"] <= turn
    ]
    continue_instruction = (
        "Continue the immediately preceding assistant response from exactly where it stopped. "
        "Do not repeat previous text. Do not add prefaces, labels, or summaries."
    )

    from app.turn_loop import prepare_gm_turn

    prepared = prepare_gm_turn(
        vault,
        scenario_id=scenario_id,
        session_id=session_id,
        user_message=continue_instruction,
        recent_limit=12,
        recent_log_override=recent_log_override,
    )

    def _on_success(appended_content: str, token_usage: dict[str, int], response_duration_ms: int) -> bytes:
        clean_appended_content = _remove_reasoning_blocks(appended_content)
        timings_ms = _response_timings(prepared, response_duration_ms)
        metadata = read_session_metadata(vault, scenario_id, session_id)
        current_turn_count = metadata.get("turn_count", 0)
        if not isinstance(current_turn_count, int) or current_turn_count < 0:
            raise ApiBadRequest("Session metadata turn_count must be a non-negative integer")
        continued_turn = max(current_turn_count, turn) + 1
        entry = append_session_log(
            vault,
            scenario_id,
            session_id,
            turn=continued_turn,
            role="assistant",
            content=clean_appended_content,
            extra={
                "continued_from_turn": turn,
                "response_duration_ms": response_duration_ms,
                "timings_ms": timings_ms,
                "segments": [
                    segment_payload(segment)
                    for segment in parse_image_markers(clean_appended_content, scenario=prepared.scenario, vault=vault)
                ],
            },
        )
        metadata["turn_count"] = continued_turn
        metadata["updated_at"] = _now_iso()
        write_session_metadata(vault, scenario_id, session_id, metadata)

        return json.dumps(
            {
                "scenario_id": scenario_id,
                "session_id": session_id,
                "turn": continued_turn,
                "continued_from_turn": turn,
                "role": "assistant",
                "appended_content": clean_appended_content,
                "entry": entry,
                "token_usage": token_usage,
                "response_duration_ms": response_duration_ms,
                "timings_ms": timings_ms,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

    if stream and hasattr(model_client, "create_chat_completion_stream"):
        def _generate() -> Iterable[bytes]:
            chunks: list[str] = []
            try:
                started = time.perf_counter()
                for chunk in model_client.create_chat_completion_stream(prepared.profile, prepared.messages):
                    if not chunk:
                        continue
                    chunks.append(chunk)
                    yield _sse_event("delta", {"delta": chunk})
                appended_content = "".join(chunks)
                yield _sse_event("final", json.loads(_on_success(appended_content, {}, _duration_ms(started))))
            except Exception as exc:
                yield _sse_event("error", {"error": type(exc).__name__, "message": str(exc)})

        return ApiStreamResponse(status=200, content_type="text/event-stream; charset=utf-8", events=_generate())

    started = time.perf_counter()
    result = model_client.create_chat_completion(prepared.profile, prepared.messages)
    response_duration_ms = _duration_ms(started)
    return ApiResponse(
        status=200,
        content_type="application/json; charset=utf-8",
        body=_on_success(result.content, getattr(result, "token_usage", {}), response_duration_ms),
    )


def _response_timings(prepared: Any, response_duration_ms: int) -> dict[str, int]:
    return _merge_timings(
        getattr(prepared, "timings_ms", None),
        {"rp_model_ms": response_duration_ms},
    )


def _merge_timings(*items: Any) -> dict[str, int]:
    merged: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        for key, value in item.items():
            if not isinstance(key, str):
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                continue
            merged[key] = value
    return merged

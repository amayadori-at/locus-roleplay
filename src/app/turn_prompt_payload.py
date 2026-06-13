from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.loaders import ModelProfile
from app.token_usage import estimate_prompt_token_usage


def latest_prompt_payload(
    *,
    scenario_id: str,
    session_id: str,
    turn: int,
    profile: ModelProfile,
    messages: list[dict[str, str]],
    rag_results: list[dict[str, Any]] | None = None,
    rag_debug: list[dict[str, Any]] | None = None,
    recent_log_selection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_payload = _request_payload(profile, messages)
    return {
        "scenario_id": scenario_id,
        "session_id": session_id,
        "turn": turn,
        "profile": {
            "id": profile.id,
            "kind": profile.kind,
            "model": profile.data.get("model"),
            "context_size": profile.data.get("context_size"),
            "temperature": profile.data.get("temperature"),
            "top_p": profile.data.get("top_p"),
            "max_tokens": profile.data.get("max_tokens"),
        },
        "request_payload": request_payload,
        "messages": messages,
        "message_count": len(messages),
        "character_count": sum(len(message.get("content", "")) for message in messages),
        "recent_log_selection": recent_log_selection or {},
        "token_usage": estimate_prompt_token_usage(messages, profile.data),
        "rag_results": rag_results or [],
        "rag_debug": rag_debug or [],
        "saved_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }


def _request_payload(profile: ModelProfile, messages: list[dict[str, str]]) -> dict[str, Any]:
    data = profile.data
    payload: dict[str, Any] = {
        "model": data.get("model"),
        "messages": messages,
    }
    for optional in (
        "temperature",
        "top_p",
        "top_k",
        "max_tokens",
        "stop",
        "frequency_penalty",
        "presence_penalty",
        "repetition_penalty",
    ):
        if optional in data:
            payload[optional] = data[optional]
    if data.get("response_format") is not None:
        payload["response_format"] = data["response_format"]
    if isinstance(data.get("reasoning_effort"), str) and data["reasoning_effort"]:
        payload["reasoning_effort"] = data["reasoning_effort"]
    return payload

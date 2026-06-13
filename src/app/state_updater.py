from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from app.loaders import ModelProfile, load_profile
from app.model_client import ChatCompletionResult
from app.state_session import (
    StatePatchError,
    deep_merge,
    parse_patch_output,
    read_session_state,
    validate_state_patch,
    write_session_state,
    write_session_state_snapshot,
)
from app.vault import Vault, VaultFileError


class StateUpdateClient(Protocol):
    def create_chat_completion(
        self, profile: ModelProfile | dict[str, Any], messages: list[dict[str, str]]
    ) -> ChatCompletionResult:
        ...


@dataclass(frozen=True)
class StateUpdateContext:
    scenario_id: str
    session_id: str
    turn: int
    current_state: dict[str, Any]
    user_message: str
    gm_response: str
    state_update_policy: str = ""
    recent_context: list[dict[str, Any]] | None = None


@dataclass(frozen=True)
class StateUpdateResult:
    updated_state: dict[str, Any]
    messages: list[dict[str, str]]
    raw_patch_output: str


def compose_state_update_messages(context: StateUpdateContext) -> list[dict[str, str]]:
    system_content = "\n".join(
        (
            "You update the current state for a roleplay session.",
            "Return valid JSON only.",
            "Do not use Markdown fences or explanations.",
            "Rules:",
            "- Output a JSON object.",
            '- Use the key "patch".',
            '- The only allowed top-level key is "patch".',
            '- The value of "patch" must be a JSON object.',
            "- Include only fields that changed.",
            "- Do not invent facts not supported by the messages.",
            '- If no state change is needed, return {"patch": {}}.',
            'Valid example: {"patch":{"flags":{"example":true}}}',
            'Invalid example: {"flags":{"example":true}}',
        )
    )
    user_sections = [
        _section("Current state", json.dumps(context.current_state, ensure_ascii=False, indent=2, sort_keys=True)),
        _section("User message", context.user_message),
        _section("GM response", context.gm_response),
        _section("State update policy", context.state_update_policy),
        _section("Recent turn context", _recent_context_text(context.recent_context or [])),
    ]
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": "\n\n".join(section for section in user_sections if section)},
    ]


def run_state_update(
    vault: Vault,
    *,
    scenario_id: str,
    session_id: str,
    turn: int,
    profile_id: str,
    user_message: str,
    gm_response: str,
    model_client: StateUpdateClient,
    recent_context: list[dict[str, Any]] | None = None,
    current_state_override: dict[str, Any] | None = None,
    persist: bool = True,
) -> StateUpdateResult:
    current_state = current_state_override if current_state_override is not None else read_session_state(vault, scenario_id, session_id)
    profile = load_profile(vault, profile_id)
    policy = _read_optional_state_update_policy(vault, scenario_id)
    messages = compose_state_update_messages(
        StateUpdateContext(
            scenario_id=scenario_id,
            session_id=session_id,
            turn=turn,
            current_state=current_state,
            user_message=user_message,
            gm_response=gm_response,
            state_update_policy=policy,
            recent_context=recent_context,
        )
    )
    completion = model_client.create_chat_completion(profile, messages)
    patch_output = _coerce_patch_output(completion.content, current_state)
    patch = parse_patch_output(patch_output)
    validate_state_patch(current_state, patch)
    updated_state = deep_merge(current_state, patch)
    if persist:
        write_session_state(vault, scenario_id, session_id, updated_state)
        write_session_state_snapshot(vault, scenario_id, session_id, turn, updated_state)
    return StateUpdateResult(updated_state=updated_state, messages=messages, raw_patch_output=completion.content)


def _coerce_patch_output(raw_output: str, current_state: dict[str, Any]) -> str | dict[str, Any]:
    try:
        return {"patch": _parse_patch(raw_output)}
    except StatePatchError as exc:
        if "must contain 'patch'" not in str(exc):
            raise

    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError:
        raise
    if not isinstance(parsed, dict):
        raise StatePatchError("State patch output root must be a JSON object")
    candidate = parsed
    if isinstance(parsed.get("state_update"), dict):
        candidate = parsed["state_update"]
    unknown_keys = set(candidate) - set(current_state)
    if unknown_keys:
        raise StatePatchError("State patch output must contain 'patch'")
    return {"patch": candidate}


def _parse_patch(raw_output: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise StatePatchError("State patch output must be valid JSON") from exc
    if not isinstance(parsed, dict):
        raise StatePatchError("State patch output root must be a JSON object")
    if "patch" not in parsed:
        raise StatePatchError("State patch output must contain 'patch'")
    patch = parsed["patch"]
    if not isinstance(patch, dict):
        raise StatePatchError("State patch field must be a JSON object")
    return patch


def _read_optional_state_update_policy(vault: Vault, scenario_id: str) -> str:
    try:
        return vault.read_text(f"rp/scenarios/{scenario_id}/gm/state_update_policy.md")
    except VaultFileError:
        return ""


def _section(title: str, content: str) -> str:
    stripped = content.strip()
    if not stripped:
        return ""
    return f"## {title}\n{stripped}"


def _recent_context_text(entries: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for entry in entries:
        role = entry.get("role")
        content = entry.get("content")
        if isinstance(role, str) and isinstance(content, str) and content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)

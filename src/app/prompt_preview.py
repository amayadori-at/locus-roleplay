from __future__ import annotations

import json
from typing import Any

from app.loaders import ModelProfile, Persona, Scenario, load_persona, load_profile, load_scenario
from app.messages import is_conversation_role
from app.prompt_graph import read_prompt_graph, read_start_prompt_graph
from app.rag import (
    DEFAULT_KEYWORD_TRIGGER_TOKEN_BUDGET,
    DEFAULT_RAG_TYPE_TOKEN_BUDGETS,
    DEFAULT_RAG_TOKEN_BUDGET,
    budget_rag_results,
    build_rag_query,
    format_rag_results,
    keyword_triggered_lore_results,
    retrieve_context,
    session_memory_results,
)
from app.reasoning import sanitize_log_entries
from app.scenario_settings import read_scenario_settings
from app.state_session import ancestor_session_ids, read_current_state, read_session_log, read_session_metadata, read_session_state
from app.token_usage import estimate_prompt_token_usage
from app.vault import Vault, VaultError


class PromptPreviewError(VaultError):
    """Raised when a prompt preview cannot be built."""


RECENT_LOG_CONTEXT_SAFETY_MARGIN = 512


def build_prompt_preview(
    vault: Vault,
    *,
    scenario_id: str,
    user_message: str,
    session_id: str | None = None,
    persona_id: str | None = None,
    profile_id: str | None = None,
    starting_id: str | None = None,
    user_note: str = "",
    session_note: str | None = None,
    scene_note: str | None = None,
    recent_limit: int = 12,
    recent_log_override: list[dict[str, Any]] | None = None,
    state_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return compose_prompt_graph(
        vault,
        scenario_id=scenario_id,
        user_message=user_message,
        session_id=session_id,
        persona_id=persona_id,
        profile_id=profile_id,
        starting_id=starting_id,
        user_note=user_note,
        session_note=session_note,
        scene_note=scene_note,
        recent_limit=recent_limit,
        recent_log_override=recent_log_override,
        state_override=state_override,
    )


def compose_prompt_graph(
    vault: Vault,
    *,
    scenario_id: str,
    user_message: str,
    session_id: str | None = None,
    persona_id: str | None = None,
    profile_id: str | None = None,
    starting_id: str | None = None,
    user_note: str = "",
    session_note: str | None = None,
    scene_note: str | None = None,
    recent_limit: int = 12,
    recent_log_override: list[dict[str, Any]] | None = None,
    state_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(user_message, str) or not user_message.strip():
        raise PromptPreviewError("user_message must be a non-empty string")

    metadata: dict[str, Any] = {}
    if session_id:
        metadata = read_session_metadata(vault, scenario_id, session_id)
        persona_id = persona_id or _metadata_string(metadata, "persona_id")
        profile_id = profile_id or _metadata_string(metadata, "rp_profile_id")
        starting_id = starting_id or _metadata_text(metadata, "starting_id") or None
        session_note = _resolved_session_note(metadata, session_note, user_note)
        scene_note = scene_note if scene_note is not None else _metadata_text(metadata, "scene_note")
    else:
        session_note = user_note if session_note is None else session_note
        scene_note = "" if scene_note is None else scene_note

    if not persona_id:
        raise PromptPreviewError("persona_id is required when session_id is not provided")
    if not profile_id:
        raise PromptPreviewError("profile_id is required when session_id is not provided")

    scenario = load_scenario(vault, scenario_id)
    persona = load_persona(vault, persona_id)
    profile = load_profile(vault, profile_id)
    if state_override is not None:
        state = state_override
    else:
        state = read_session_state(vault, scenario_id, session_id) if session_id else read_current_state(vault, scenario_id)
    if recent_log_override is not None:
        raw_recent_log = sanitize_log_entries(recent_log_override)
    else:
        raw_recent_log = sanitize_log_entries(read_session_log(vault, scenario_id, session_id) if session_id else [])
    graph_info = _select_prompt_graph(vault, scenario_id, starting_id)
    graph = graph_info["graph"]

    active_mods: list[str] = _safe_string_list(metadata.get("active_mods"))
    pinned_characters: list[str] = _safe_string_list(metadata.get("pinned_characters"))
    allowed_memory_session_ids = set(ancestor_session_ids(vault, scenario_id, session_id)) if session_id else None
    current_turn = _metadata_turn_count(metadata)

    base_messages, _base_expansions = _compose_messages_from_graph(
        vault,
        graph=graph,
        scenario=scenario,
        persona=persona,
        state=state,
        recent_log=[],
        session_note=session_note,
        scene_note=scene_note,
        user_message=user_message,
        active_mods=active_mods,
        pinned_characters=pinned_characters,
        allowed_memory_session_ids=allowed_memory_session_ids,
        current_turn=current_turn,
    )
    recent_log, recent_log_selection = _select_recent_log_for_context(
        raw_recent_log,
        profile.data,
        base_messages=base_messages,
        recent_limit=recent_limit,
    )
    messages, expansions = _compose_messages_from_graph(
        vault,
        graph=graph,
        scenario=scenario,
        persona=persona,
        state=state,
        recent_log=recent_log,
        session_note=session_note,
        scene_note=scene_note,
        user_message=user_message,
        active_mods=active_mods,
        pinned_characters=pinned_characters,
        allowed_memory_session_ids=allowed_memory_session_ids,
        current_turn=current_turn,
    )

    token_usage = estimate_prompt_token_usage(messages, profile.data)
    return {
        "scenario_id": scenario_id,
        "session_id": session_id,
        "persona_id": persona.id,
        "profile": _profile_summary(profile),
        "graph": {
            "id": graph["id"],
            "version": graph["version"],
            "source": graph_info["source"],
            "starting_id": graph_info["starting_id"],
            "own_graph": graph_info["own_graph"],
        },
        "expansions": expansions,
        "messages": messages,
        "message_count": len(messages),
        "character_count": sum(len(message.get("content", "")) for message in messages),
        "token_usage": token_usage,
        "recent_log_selection": recent_log_selection,
        "selected_recent_log": recent_log,
    }


def _select_prompt_graph(vault: Vault, scenario_id: str, starting_id: str | None) -> dict[str, Any]:
    settings = read_scenario_settings(vault, scenario_id)
    if settings.get("prompt_graph_mode") == "per_start" and starting_id:
        result = read_start_prompt_graph(vault, scenario_id, starting_id)
        return {
            "graph": result["graph"],
            "source": result["source"],
            "starting_id": starting_id,
            "own_graph": result["own_graph"],
        }
    return {
        "graph": read_prompt_graph(vault, scenario_id),
        "source": "scenario",
        "starting_id": None,
        "own_graph": True,
    }


def _compose_messages_from_graph(
    vault: Vault,
    *,
    graph: dict[str, Any],
    scenario: Scenario,
    persona: Persona,
    state: dict[str, Any],
    recent_log: list[dict[str, Any]],
    session_note: str,
    scene_note: str,
    user_message: str,
    active_mods: list[str],
    pinned_characters: list[str],
    allowed_memory_session_ids: set[str] | None = None,
    current_turn: int | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    system_sections: list[str] = []
    conversation_messages: list[dict[str, str]] = []
    expansions: list[dict[str, Any]] = []

    for node in graph["nodes"]:
        expansion = _expand_node(
            vault,
            node=node,
            scenario=scenario,
            persona=persona,
            state=state,
            recent_log=recent_log,
            session_note=session_note,
            scene_note=scene_note,
            user_message=user_message,
            active_mods=active_mods,
            pinned_characters=pinned_characters,
            allowed_memory_session_ids=allowed_memory_session_ids,
            current_turn=current_turn,
        )
        expansions.append(expansion)
        if not expansion["included"]:
            continue
        role = expansion["role"]
        content = expansion["content"]
        if role == "system":
            section = _section(expansion["title"], content)
            if section:
                system_sections.append(section)
        elif role == "messages":
            for item in expansion.get("messages", []):
                item_role = item.get("role")
                item_content = item.get("content")
                if is_conversation_role(item_role) and isinstance(item_content, str) and item_content:
                    conversation_messages.append({"role": item_role, "content": item_content})
        elif role in {"user", "assistant"} and content:
            conversation_messages.append({"role": role, "content": content})

    messages: list[dict[str, str]] = []
    if system_sections:
        messages.append({"role": "system", "content": "\n\n".join(system_sections)})
    messages.extend(conversation_messages)

    return messages, expansions


def _select_recent_log_for_context(
    recent_log: list[dict[str, Any]],
    profile_data: dict[str, Any],
    *,
    base_messages: list[dict[str, str]],
    recent_limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    conversation_entries = [
        entry
        for entry in recent_log
        if is_conversation_role(entry.get("role")) and isinstance(entry.get("content"), str) and entry.get("content")
    ]
    max_entries = recent_limit if isinstance(recent_limit, int) and not isinstance(recent_limit, bool) and recent_limit >= 0 else 12
    if max_entries == 0 or not conversation_entries:
        return [], _recent_log_selection_payload(
            selected=[],
            available_tokens=0,
            considered_count=len(conversation_entries),
            dropped_count=len(conversation_entries),
            reason="recent_limit_zero" if max_entries == 0 else "empty_log",
        )

    capped_entries = conversation_entries[-max_entries:]
    context_size = _optional_int(profile_data.get("context_size"))
    if context_size is None:
        return capped_entries, _recent_log_selection_payload(
            selected=capped_entries,
            available_tokens=None,
            considered_count=len(capped_entries),
            dropped_count=0,
            reason="context_size_missing",
        )

    base_usage = estimate_prompt_token_usage(base_messages, profile_data)
    reserved = _optional_int(profile_data.get("max_tokens")) or 0
    available = context_size - reserved - int(base_usage.get("prompt_tokens", 0)) - RECENT_LOG_CONTEXT_SAFETY_MARGIN
    if available <= 0:
        return [], _recent_log_selection_payload(
            selected=[],
            available_tokens=max(0, available),
            considered_count=len(capped_entries),
            dropped_count=len(capped_entries),
            reason="no_available_context",
        )

    selected_reversed: list[dict[str, Any]] = []
    used = 0
    for entry in reversed(capped_entries):
        role = entry.get("role")
        content = entry.get("content")
        if not is_conversation_role(role) or not isinstance(content, str) or not content:
            continue
        usage = estimate_prompt_token_usage([{"role": role, "content": content}], {})["prompt_tokens"]
        if selected_reversed and used + usage > available:
            break
        if not selected_reversed and usage > available:
            break
        selected_reversed.append(entry)
        used += usage

    selected = list(reversed(selected_reversed))
    return selected, _recent_log_selection_payload(
        selected=selected,
        available_tokens=available,
        considered_count=len(capped_entries),
        dropped_count=len(capped_entries) - len(selected),
        reason="token_budget",
        selected_tokens=used,
    )


def _recent_log_selection_payload(
    *,
    selected: list[dict[str, Any]],
    available_tokens: int | None,
    considered_count: int,
    dropped_count: int,
    reason: str,
    selected_tokens: int | None = None,
) -> dict[str, Any]:
    if selected_tokens is None:
        selected_tokens = sum(
            estimate_prompt_token_usage(
                [
                    {
                        "role": str(entry.get("role") or ""),
                        "content": str(entry.get("content") or ""),
                    }
                ],
                {},
            )["prompt_tokens"]
            for entry in selected
        )
    return {
        "strategy": "token_budget",
        "reason": reason,
        "available_tokens": available_tokens,
        "selected_tokens": selected_tokens,
        "selected_count": len(selected),
        "considered_count": considered_count,
        "dropped_count": max(0, dropped_count),
    }


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


def _expand_node(
    vault: Vault,
    *,
    node: dict[str, Any],
    scenario: Scenario,
    persona: Persona,
    state: dict[str, Any],
    recent_log: list[dict[str, Any]],
    session_note: str,
    scene_note: str,
    user_message: str,
    active_mods: list[str] | None = None,
    pinned_characters: list[str] | None = None,
    allowed_memory_session_ids: set[str] | None = None,
    current_turn: int | None = None,
) -> dict[str, Any]:
    node_id = node["id"]
    node_type = node["type"]
    role = node["role"]
    base = {
        "node_id": node_id,
        "type": node_type,
        "role": role,
        "order": node["order"],
        "title": _node_title(node),
        "included": True,
        "skipped_reason": "",
        "content": "",
        "content_tokens": 0,
    }

    if not _condition_matches(node.get("condition"), scenario):
        return {**base, "included": False, "skipped_reason": "condition_not_met"}

    if node_type == "file":
        content = _file_node_content(vault, scenario, node)
    elif node_type == "selected_persona":
        content = _persona_text(persona)
    elif node_type == "user_note":
        content = session_note
        if not content.strip():
            return {**base, "included": False, "skipped_reason": "empty_session_note"}
    elif node_type == "scene_note":
        content = scene_note
        if not content.strip():
            return {**base, "included": False, "skipped_reason": "empty_scene_note"}
    elif node_type == "state":
        content = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True)
    elif node_type == "active_mods":
        content, warnings = _load_pinned_files(vault, scenario.id, active_mods or [], "lore", require_mod=True)
        if not content.strip():
            return {**base, "included": False, "skipped_reason": "no_active_mods", "pin_warnings": warnings}
        return {
            **base,
            "content": content,
            "content_tokens": estimate_prompt_token_usage([{"role": role if role != "messages" else "user", "content": content}], {})["prompt_tokens"],
            "pin_warnings": warnings,
        }
    elif node_type == "pinned_characters":
        content, warnings = _load_pinned_files(vault, scenario.id, pinned_characters or [], "characters", require_mod=False)
        if not content.strip():
            return {**base, "included": False, "skipped_reason": "no_pinned_characters", "pin_warnings": warnings}
        return {
            **base,
            "content": content,
            "content_tokens": estimate_prompt_token_usage([{"role": role if role != "messages" else "user", "content": content}], {})["prompt_tokens"],
            "pin_warnings": warnings,
        }
    elif node_type == "rag":
        exclude_paths: set[str] = set(active_mods or []) | set(pinned_characters or [])
        query = build_rag_query(user_message=user_message, recent_log=recent_log, state=state)
        sources = _node_sources(node)
        limit = _node_limit(node)
        limits = _node_limits(node)
        token_budget = _node_token_budget(node)
        session_memory: list[dict[str, Any]] = []
        if "memory" in sources and allowed_memory_session_ids:
            session_memory = session_memory_results(
                vault,
                scenario.id,
                allowed_session_ids=allowed_memory_session_ids,
                exclude_paths=exclude_paths if exclude_paths else None,
            )
        session_memory_paths = {
            result["source_path"] for result in session_memory if isinstance(result.get("source_path"), str)
        }
        keyword_results: list[dict[str, Any]] = []
        keyword_warnings: list[str] = []
        if "lore" in sources:
            keyword_results, keyword_warnings = keyword_triggered_lore_results(
                vault,
                scenario.id,
                user_message=user_message,
                recent_log=recent_log,
                exclude_paths=exclude_paths if exclude_paths else None,
            )
        keyword_paths = {result["source_path"] for result in keyword_results if isinstance(result.get("source_path"), str)}
        retrieval_exclude_paths = exclude_paths | keyword_paths | session_memory_paths
        results = retrieve_context(
            vault,
            scenario_id=scenario.id,
            query=query,
            limit=limit,
            sources=sources,
            exclude_paths=retrieval_exclude_paths if retrieval_exclude_paths else None,
            character_match_mode=_character_rag_match_mode(scenario.metadata),
            limits=limits,
            allowed_session_ids=allowed_memory_session_ids,
            current_turn=current_turn,
        )
        keyword_budgeted_results = budget_rag_results(
            keyword_results,
            token_budget=_node_keyword_token_budget(node),
            token_budgets={"lore": _node_keyword_token_budget(node)},
        )
        budgeted_results = budget_rag_results(
            session_memory + results,
            token_budget=token_budget,
            token_budgets=_node_token_budgets(node),
        )
        combined_results = keyword_budgeted_results + budgeted_results
        content = format_rag_results(combined_results)
        if not content:
            reason = "rag_budget_exhausted" if results or session_memory else "no_rag_results"
            return {
                **base,
                "included": False,
                "skipped_reason": reason,
                "results": [],
                "session_memory_results": [],
                "keyword_results": [],
                "keyword_warnings": keyword_warnings,
                "query": query,
                "sources": sources,
                "limit": limit,
                "retrieved_count": len(results),
                "included_count": 0,
                "token_budget": token_budget,
                "keyword_token_budget": _node_keyword_token_budget(node),
                "token_budgets": _node_effective_token_budgets(node),
                **({"limits": limits} if limits else {}),
            }
        return {
            **base,
            "content": content,
            "content_tokens": estimate_prompt_token_usage([{"role": role if role != "messages" else "user", "content": content}], {})[
                "prompt_tokens"
            ],
            "results": combined_results,
            "session_memory_results": session_memory,
            "keyword_results": keyword_budgeted_results,
            "keyword_warnings": keyword_warnings,
            "query": query,
            "sources": sources,
            "limit": limit,
            "retrieved_count": len(results),
            "included_count": len(combined_results),
            "token_budget": token_budget,
            "keyword_token_budget": _node_keyword_token_budget(node),
            "token_budgets": _node_effective_token_budgets(node),
            **({"limits": limits} if limits else {}),
        }
    elif node_type == "session_log":
        messages = [
            {"role": entry["role"], "content": entry["content"]}
            for entry in recent_log
            if is_conversation_role(entry.get("role")) and isinstance(entry.get("content"), str) and entry.get("content")
        ]
        return {**base, "messages": messages, "content": "", "content_tokens": 0}
    elif node_type == "current_user_message":
        content = user_message
    else:
        return {**base, "included": False, "skipped_reason": "node_type_not_expandable"}

    return {
        **base,
        "content": content,
        "content_tokens": estimate_prompt_token_usage([{"role": role if role != "messages" else "user", "content": content}], {})[
            "prompt_tokens"
        ],
    }


def _load_pinned_files(
    vault: "Vault",
    scenario_id: str,
    paths: list[str],
    expected_folder: str,
    *,
    require_mod: bool,
) -> tuple[str, list[str]]:
    """Load pinned files and return (combined_content, warnings).

    Skips files that are unsafe, not found, or (when require_mod=True) missing mod: true.
    """
    from app.rag import load_scenario_file

    sections: list[str] = []
    warnings: list[str] = []
    for raw_path in paths:
        if not isinstance(raw_path, str):
            continue
        parts = raw_path.split("/")
        if (
            "\\" in raw_path
            or any(p in ("", ".", "..") for p in parts)
            or len(parts) != 2
            or parts[0] != expected_folder
            or not parts[1].endswith(".md")
        ):
            warnings.append(f"{raw_path}: invalid path")
            continue
        doc = load_scenario_file(vault, scenario_id, raw_path)
        if doc is None:
            warnings.append(f"{raw_path}: file not found")
            continue
        if require_mod and doc.metadata.get("mod") is not True:
            warnings.append(f"{raw_path}: mod: true not set")
            continue
        title = doc.title or parts[1].removesuffix(".md")
        body = doc.body.strip()
        if body:
            sections.append(f"### {title}\n{body}")
    return "\n\n".join(sections), warnings


def _safe_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _file_node_content(vault: Vault, scenario: Scenario, node: dict[str, Any]) -> str:
    path = node.get("path")
    if path == "system_prompt.md":
        return scenario.system_prompt
    if path == "scenario.md":
        return _scenario_text(scenario)
    if path == "gm/gm_system.md":
        return scenario.gm_system
    if path == "gm/narration_policy.md":
        return scenario.narration_policy
    if path == "gm/image_policy.md":
        return scenario.image_policy or json.dumps(
            {
                "image_enabled": scenario.metadata.get("image_enabled"),
                "image_mode": scenario.metadata.get("image_mode"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    return vault.read_text(f"rp/scenarios/{scenario.id}/{path}")


def _condition_matches(condition: object, scenario: Scenario) -> bool:
    if condition is None:
        return True
    if not isinstance(condition, dict):
        return False
    for key, expected in condition.items():
        if key == "scenario.image_enabled" and scenario.metadata.get("image_enabled") != expected:
            return False
    return True


def _node_limit(node: dict[str, Any]) -> int:
    value = node.get("limit", 6)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 6


def _node_limits(node: dict[str, Any]) -> dict[str, int] | None:
    """Optional per-type count limits. Returns None when unset/invalid (shared limit applies)."""
    value = node.get("limits")
    if not isinstance(value, dict):
        return None
    limits: dict[str, int] = {}
    for key, cap in value.items():
        if isinstance(key, str) and key.strip() and isinstance(cap, int) and not isinstance(cap, bool) and cap >= 0:
            limits[key] = cap
    return limits or None


def _node_sources(node: dict[str, Any]) -> list[str]:
    value = node.get("source")
    if not isinstance(value, list):
        return ["memory", "lore", "characters"]
    return [item for item in value if isinstance(item, str)]


def _node_budget_enabled(node: dict[str, Any]) -> bool:
    return node.get("budget_enabled") is not False


def _node_token_budget(node: dict[str, Any]) -> int | None:
    if not _node_budget_enabled(node):
        return None
    value = node.get("token_budget", DEFAULT_RAG_TOKEN_BUDGET)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else DEFAULT_RAG_TOKEN_BUDGET


def _node_keyword_token_budget(node: dict[str, Any]) -> int | None:
    if not _node_budget_enabled(node):
        return None
    value = node.get("keyword_token_budget", DEFAULT_KEYWORD_TRIGGER_TOKEN_BUDGET)
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return DEFAULT_KEYWORD_TRIGGER_TOKEN_BUDGET


def _node_token_budgets(node: dict[str, Any]) -> dict[str, int | None]:
    if not _node_budget_enabled(node):
        return {key: None for key in DEFAULT_RAG_TYPE_TOKEN_BUDGETS}
    value = node.get("token_budgets")
    if not isinstance(value, dict):
        return {}
    budgets: dict[str, int | None] = {}
    for key, budget in value.items():
        if isinstance(key, str) and isinstance(budget, int) and not isinstance(budget, bool) and budget >= 0:
            budgets[key] = budget
    return budgets


def _node_effective_token_budgets(node: dict[str, Any]) -> dict[str, int | None]:
    if not _node_budget_enabled(node):
        return {key: None for key in DEFAULT_RAG_TYPE_TOKEN_BUDGETS}
    return {**DEFAULT_RAG_TYPE_TOKEN_BUDGETS, **_node_token_budgets(node)}


def _character_rag_match_mode(metadata: dict[str, Any]) -> str:
    config = metadata.get("character_rag")
    if isinstance(config, dict):
        value = config.get("match")
        if isinstance(value, str) and value.strip().lower() == "fuzzy":
            return "fuzzy"
        return "exact"
    return "exact"


def _section(title: str, content: str) -> str:
    stripped = content.strip()
    if not stripped:
        return ""
    return f"## {title}\n{stripped}"


def _node_title(node: dict[str, Any]) -> str:
    titles = {
        "system_prompt": "System Prompt",
        "gm_system": "GM Policy",
        "narration_policy": "Narration Policy",
        "scenario": "Scenario",
        "active_mods": "Active Mods",
        "selected_persona": "User Persona",
        "user_note": "Session User Note",
        "scene_note": "Scene Note",
        "current_state": "Current State",
        "pinned_characters": "Pinned Characters",
        "retrieved_lore_memory": "Relevant Lore / Memory",
        "image_policy": "Image Policy",
        "recent_log": "Recent Conversation",
        "current_user_message": "Current User Message",
    }
    return titles.get(node.get("id"), str(node.get("id", "Prompt Node")))


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


def _profile_summary(profile: ModelProfile) -> dict[str, Any]:
    return {
        "id": profile.id,
        "kind": profile.kind,
        "model": profile.data.get("model"),
        "context_size": profile.data.get("context_size"),
        "temperature": profile.data.get("temperature"),
        "top_p": profile.data.get("top_p"),
        "max_tokens": profile.data.get("max_tokens"),
    }


def _metadata_string(metadata: dict[str, Any], field: str) -> str:
    value = metadata.get(field)
    if not isinstance(value, str) or not value.strip():
        raise PromptPreviewError(f"Session metadata field is missing or invalid: {field}")
    return value


def _metadata_text(metadata: dict[str, Any], field: str) -> str:
    value = metadata.get(field)
    return value if isinstance(value, str) else ""


def _metadata_turn_count(metadata: dict[str, Any]) -> int | None:
    value = metadata.get("turn_count")
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _resolved_session_note(metadata: dict[str, Any], session_note: str | None, legacy_user_note: str = "") -> str:
    if session_note is not None:
        return session_note
    if legacy_user_note:
        return legacy_user_note
    return _metadata_text(metadata, "session_note") or _metadata_text(metadata, "user_note")

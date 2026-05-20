from __future__ import annotations

import json
from typing import Any

from app.loaders import ModelProfile, Persona, Scenario, load_persona, load_profile, load_scenario
from app.messages import is_conversation_role
from app.prompt_graph import read_prompt_graph
from app.rag import DEFAULT_RAG_TOKEN_BUDGET, budget_rag_results, build_rag_query, format_rag_results, load_scenario_file, retrieve_context
from app.state_session import read_current_state, read_session_log, read_session_metadata, read_session_state
from app.token_usage import estimate_prompt_token_usage
from app.vault import Vault, VaultError


class PromptPreviewError(VaultError):
    """Raised when a prompt preview cannot be built."""


def build_prompt_preview(
    vault: Vault,
    *,
    scenario_id: str,
    user_message: str,
    session_id: str | None = None,
    persona_id: str | None = None,
    profile_id: str | None = None,
    user_note: str = "",
    recent_limit: int = 12,
    recent_log_override: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return compose_prompt_graph(
        vault,
        scenario_id=scenario_id,
        user_message=user_message,
        session_id=session_id,
        persona_id=persona_id,
        profile_id=profile_id,
        user_note=user_note,
        recent_limit=recent_limit,
        recent_log_override=recent_log_override,
    )


def compose_prompt_graph(
    vault: Vault,
    *,
    scenario_id: str,
    user_message: str,
    session_id: str | None = None,
    persona_id: str | None = None,
    profile_id: str | None = None,
    user_note: str = "",
    recent_limit: int = 12,
    recent_log_override: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not isinstance(user_message, str) or not user_message.strip():
        raise PromptPreviewError("user_message must be a non-empty string")

    metadata: dict[str, Any] = {}
    if session_id:
        metadata = read_session_metadata(vault, scenario_id, session_id)
        persona_id = persona_id or _metadata_string(metadata, "persona_id")
        profile_id = profile_id or _metadata_string(metadata, "rp_profile_id")
        user_note = user_note or _metadata_text(metadata, "user_note")

    if not persona_id:
        raise PromptPreviewError("persona_id is required when session_id is not provided")
    if not profile_id:
        raise PromptPreviewError("profile_id is required when session_id is not provided")

    scenario = load_scenario(vault, scenario_id)
    persona = load_persona(vault, persona_id)
    profile = load_profile(vault, profile_id)
    state = read_session_state(vault, scenario_id, session_id) if session_id else read_current_state(vault, scenario_id)
    if recent_log_override is not None:
        recent_log = recent_log_override
    else:
        recent_log = read_session_log(vault, scenario_id, session_id, limit=recent_limit) if session_id else []
    graph = read_prompt_graph(vault, scenario_id)

    active_mods: list[str] = _safe_string_list(metadata.get("active_mods"))
    pinned_characters: list[str] = _safe_string_list(metadata.get("pinned_characters"))

    messages: list[dict[str, str]] = []
    system_sections: list[str] = []
    expansions: list[dict[str, Any]] = []

    for node in graph["nodes"]:
        expansion = _expand_node(
            vault,
            node=node,
            scenario=scenario,
            persona=persona,
            state=state,
            recent_log=recent_log,
            user_note=user_note,
            user_message=user_message,
            active_mods=active_mods,
            pinned_characters=pinned_characters,
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
                    messages.append({"role": item_role, "content": item_content})
        elif role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})

    if system_sections:
        messages.insert(0, {"role": "system", "content": "\n\n".join(system_sections)})

    return {
        "scenario_id": scenario_id,
        "session_id": session_id,
        "persona_id": persona.id,
        "profile": _profile_summary(profile),
        "graph": {"id": graph["id"], "version": graph["version"]},
        "expansions": expansions,
        "messages": messages,
        "message_count": len(messages),
        "character_count": sum(len(message.get("content", "")) for message in messages),
        "token_usage": estimate_prompt_token_usage(messages, profile.data),
    }


def _expand_node(
    vault: Vault,
    *,
    node: dict[str, Any],
    scenario: Scenario,
    persona: Persona,
    state: dict[str, Any],
    recent_log: list[dict[str, Any]],
    user_note: str,
    user_message: str,
    active_mods: list[str] | None = None,
    pinned_characters: list[str] | None = None,
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
        content = user_note
        if not content.strip():
            return {**base, "included": False, "skipped_reason": "empty_user_note"}
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
        token_budget = _node_token_budget(node)
        results = retrieve_context(
            vault,
            scenario_id=scenario.id,
            query=query,
            limit=limit,
            sources=sources,
            exclude_paths=exclude_paths if exclude_paths else None,
        )
        budgeted_results = budget_rag_results(
            results,
            token_budget=token_budget,
            token_budgets=_node_token_budgets(node),
        )
        content = format_rag_results(budgeted_results)
        if not content:
            reason = "rag_budget_exhausted" if results else "no_rag_results"
            return {
                **base,
                "included": False,
                "skipped_reason": reason,
                "results": [],
                "query": query,
                "sources": sources,
                "limit": limit,
                "retrieved_count": len(results),
                "included_count": 0,
                "token_budget": token_budget,
            }
        return {
            **base,
            "content": content,
            "content_tokens": estimate_prompt_token_usage([{"role": role if role != "messages" else "user", "content": content}], {})[
                "prompt_tokens"
            ],
            "results": budgeted_results,
            "query": query,
            "sources": sources,
            "limit": limit,
            "retrieved_count": len(results),
            "included_count": len(budgeted_results),
            "token_budget": token_budget,
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


def _node_sources(node: dict[str, Any]) -> list[str]:
    value = node.get("source")
    if not isinstance(value, list):
        return ["memory", "lore", "characters"]
    return [item for item in value if isinstance(item, str)]


def _node_token_budget(node: dict[str, Any]) -> int:
    value = node.get("token_budget", DEFAULT_RAG_TOKEN_BUDGET)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else DEFAULT_RAG_TOKEN_BUDGET


def _node_token_budgets(node: dict[str, Any]) -> dict[str, int]:
    value = node.get("token_budgets")
    if not isinstance(value, dict):
        return {}
    budgets: dict[str, int] = {}
    for key, budget in value.items():
        if isinstance(key, str) and isinstance(budget, int) and not isinstance(budget, bool) and budget >= 0:
            budgets[key] = budget
    return budgets


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

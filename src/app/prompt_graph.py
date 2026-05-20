from __future__ import annotations

import copy
import json
from pathlib import PurePosixPath
from typing import Any

from app.ids import is_locus_id
from app.loaders import load_scenario
from app.vault import Vault, VaultError, VaultFileError


PROMPT_GRAPH_VERSION = 1
PROMPT_GRAPH_ROLES = frozenset({"system", "user", "assistant", "messages"})
PROMPT_GRAPH_NODE_TYPES = frozenset(
    {
        "file",
        "selected_persona",
        "state",
        "rag",
        "active_mods",
        "pinned_characters",
        "session_log",
        "user_note",
        "current_user_message",
        "condition",
        "output",
    }
)
REQUIRED_NODE_IDS = frozenset({"system_prompt", "selected_persona", "current_state", "recent_log", "current_user_message"})


class PromptGraphError(VaultError):
    """Raised when a prompt graph is missing, invalid, or unsafe."""


def default_prompt_graph() -> dict[str, Any]:
    return {
        "id": "default",
        "version": PROMPT_GRAPH_VERSION,
        "nodes": [
            _node("system_prompt", "file", 10, role="system", required=True, path="system_prompt.md"),
            _node("gm_system", "file", 20, role="system", required=False, path="gm/gm_system.md"),
            _node("narration_policy", "file", 30, role="system", required=False, path="gm/narration_policy.md"),
            _node("scenario", "file", 40, role="system", required=True, path="scenario.md"),
            _node("active_mods", "active_mods", 45, role="system", required=False),
            _node("selected_persona", "selected_persona", 50, role="system", required=True),
            _node("user_note", "user_note", 60, role="system", required=False),
            _node("current_state", "state", 70, role="system", required=True),
            _node("pinned_characters", "pinned_characters", 77, role="system", required=False),
            {
                "id": "retrieved_lore_memory",
                "type": "rag",
                "source": ["memory", "lore", "characters"],
                "role": "system",
                "required": False,
                "order": 80,
                "limit": 6,
                "token_budget": 6000,
                "token_budgets": {
                    "memory": 2400,
                    "lore": 2400,
                    "character": 1800,
                },
            },
            {
                "id": "image_policy",
                "type": "file",
                "path": "gm/image_policy.md",
                "role": "system",
                "required": False,
                "order": 90,
                "condition": {"scenario.image_enabled": True},
            },
            _node("recent_log", "session_log", 100, role="messages", required=True, token_budget=12000),
            _node("current_user_message", "current_user_message", 110, role="user", required=True),
        ],
    }


def read_prompt_graph(vault: Vault, scenario_id: str) -> dict[str, Any]:
    _validate_scenario_id(scenario_id)
    load_scenario(vault, scenario_id)
    graph_path = vault.resolve(_prompt_graph_path(scenario_id))
    if not graph_path.exists():
        return validate_prompt_graph(vault, scenario_id, default_prompt_graph())
    try:
        raw = vault.load_json(_prompt_graph_path(scenario_id))
    except VaultFileError as exc:
        raise PromptGraphError(f"Prompt graph is unreadable: {_prompt_graph_path(scenario_id)}") from exc
    validated = validate_prompt_graph(vault, scenario_id, raw)
    return _inject_missing_pin_nodes(validated)


def _inject_missing_pin_nodes(graph: dict[str, Any]) -> dict[str, Any]:
    """Add active_mods / pinned_characters nodes when they are absent from a stored graph.

    This silently upgrades graphs saved before these node types were introduced, without
    modifying the file on disk.  Duplicate-order conflicts are resolved by bumping by 1.
    """
    existing_types = {node["type"] for node in graph.get("nodes", [])}
    if "active_mods" in existing_types and "pinned_characters" in existing_types:
        return graph

    existing_orders = {node["order"] for node in graph.get("nodes", [])}
    nodes = list(graph["nodes"])

    def _safe_order(preferred: int) -> int:
        order = preferred
        while order in existing_orders:
            order += 1
        existing_orders.add(order)
        return order

    if "active_mods" not in existing_types:
        nodes.append(_node("active_mods", "active_mods", _safe_order(45), role="system", required=False))
    if "pinned_characters" not in existing_types:
        nodes.append(_node("pinned_characters", "pinned_characters", _safe_order(77), role="system", required=False))

    return {**graph, "nodes": sorted(nodes, key=lambda n: (n["order"], n["id"]))}


def write_prompt_graph(vault: Vault, scenario_id: str, graph: dict[str, Any]) -> dict[str, Any]:
    normalized = validate_prompt_graph(vault, scenario_id, graph)
    path = vault.resolve(_prompt_graph_path(scenario_id))
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(normalized, ensure_ascii=False, indent=2) + "\n"
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        temp_path.write_text(raw, encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return normalized


def validate_prompt_graph(vault: Vault, scenario_id: str, graph: object) -> dict[str, Any]:
    _validate_scenario_id(scenario_id)
    if not isinstance(graph, dict):
        raise PromptGraphError("Prompt graph root must be a JSON object")
    graph_id = graph.get("id")
    if not isinstance(graph_id, str) or not graph_id.strip():
        raise PromptGraphError("Prompt graph id must be a non-empty string")
    version = graph.get("version", PROMPT_GRAPH_VERSION)
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise PromptGraphError("Prompt graph version must be a positive integer")
    nodes = graph.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise PromptGraphError("Prompt graph nodes must be a non-empty array")

    normalized_nodes = [_validate_node(vault, scenario_id, node, index) for index, node in enumerate(nodes)]
    ids = [node["id"] for node in normalized_nodes]
    duplicate_ids = sorted({node_id for node_id in ids if ids.count(node_id) > 1})
    if duplicate_ids:
        raise PromptGraphError(f"Prompt graph contains duplicate node id(s): {', '.join(duplicate_ids)}")
    orders = [node["order"] for node in normalized_nodes]
    duplicate_orders = sorted({order for order in orders if orders.count(order) > 1})
    if duplicate_orders:
        formatted = ", ".join(str(order) for order in duplicate_orders)
        raise PromptGraphError(f"Prompt graph contains duplicate order value(s): {formatted}")
    missing_required = sorted(REQUIRED_NODE_IDS - set(ids))
    if missing_required:
        raise PromptGraphError(f"Prompt graph is missing required node id(s): {', '.join(missing_required)}")

    normalized = copy.deepcopy(graph)
    normalized["id"] = graph_id
    normalized["version"] = version
    normalized["nodes"] = sorted(normalized_nodes, key=lambda node: (node["order"], node["id"]))
    if "edges" in graph:
        normalized["edges"] = _validate_edges(normalized_nodes, graph["edges"])
    return normalized


def prompt_graph_warnings(vault: Vault, scenario_id: str, graph: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for node in graph.get("nodes", []):
        if not isinstance(node, dict) or node.get("type") != "file":
            continue
        path = node.get("path")
        if not isinstance(path, str):
            continue
        exists = vault.resolve(f"rp/scenarios/{scenario_id}/{path}").is_file()
        if not exists and node.get("required") is not True:
            warnings.append(f"Optional file node '{node.get('id')}' is missing: {path}")
    return warnings


def _validate_node(vault: Vault, scenario_id: str, node: object, index: int) -> dict[str, Any]:
    if not isinstance(node, dict):
        raise PromptGraphError(f"Prompt graph node at index {index} must be an object")
    node_id = _required_string(node, "id", index)
    if not is_locus_id(node_id):
        raise PromptGraphError(f"Prompt graph node id is invalid: {node_id}")
    node_type = _required_string(node, "type", index)
    if node_type not in PROMPT_GRAPH_NODE_TYPES:
        raise PromptGraphError(f"Prompt graph node '{node_id}' has unsupported type: {node_type}")
    role = _required_string(node, "role", index)
    if role not in PROMPT_GRAPH_ROLES:
        raise PromptGraphError(f"Prompt graph node '{node_id}' has unsupported role: {role}")
    order = node.get("order")
    if not isinstance(order, (int, float)) or isinstance(order, bool):
        raise PromptGraphError(f"Prompt graph node '{node_id}' order must be a number")
    required = node.get("required", False)
    if not isinstance(required, bool):
        raise PromptGraphError(f"Prompt graph node '{node_id}' required must be a boolean")

    normalized = copy.deepcopy(node)
    normalized["id"] = node_id
    normalized["type"] = node_type
    normalized["role"] = role
    normalized["order"] = order
    normalized["required"] = required

    if node_type == "file":
        source_path = _validate_source_path(_required_string(node, "path", index), node_id)
        normalized["path"] = source_path
        path = vault.resolve(f"rp/scenarios/{scenario_id}/{source_path}")
        if required and not path.is_file():
            raise PromptGraphError(f"Required file node '{node_id}' does not exist: {source_path}")
    if "token_budget" in node and (
        not isinstance(node["token_budget"], (int, float)) or isinstance(node["token_budget"], bool) or node["token_budget"] < 0
    ):
        raise PromptGraphError(f"Prompt graph node '{node_id}' token_budget must be a non-negative number")
    if "token_budgets" in node:
        _validate_token_budgets(node_id, node["token_budgets"])
    return normalized


def _validate_source_path(value: str, node_id: str) -> str:
    if "\\" in value:
        raise PromptGraphError(f"Prompt graph node '{node_id}' path must not contain backslashes")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise PromptGraphError(f"Prompt graph node '{node_id}' path contains an unsafe segment")
    normalized = path.as_posix()
    if not _is_allowed_prompt_source_path(normalized):
        raise PromptGraphError(f"Prompt graph node '{node_id}' path is not an allowed scenario source: {normalized}")
    return normalized


def _is_allowed_prompt_source_path(value: str) -> bool:
    path = PurePosixPath(value)
    parts = path.parts
    if len(parts) == 1:
        return parts[0] in {"scenario.md", "system_prompt.md"}
    if len(parts) == 2 and parts[1].endswith(".md"):
        return parts[0] in {"gm", "characters", "lore"} and is_locus_id(parts[1].removesuffix(".md"))
    return False


def _required_string(node: dict[str, Any], field: str, index: int) -> str:
    value = node.get(field)
    if not isinstance(value, str) or not value.strip():
        raise PromptGraphError(f"Prompt graph node at index {index} field '{field}' must be a non-empty string")
    return value


def _validate_token_budgets(node_id: str, value: object) -> None:
    if not isinstance(value, dict):
        raise PromptGraphError(f"Prompt graph node '{node_id}' token_budgets must be an object")
    for key, budget in value.items():
        if not isinstance(key, str) or not key.strip():
            raise PromptGraphError(f"Prompt graph node '{node_id}' token_budgets keys must be non-empty strings")
        if not isinstance(budget, (int, float)) or isinstance(budget, bool) or budget < 0:
            raise PromptGraphError(f"Prompt graph node '{node_id}' token_budgets values must be non-negative numbers")


def _validate_edges(nodes: list[dict[str, Any]], value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise PromptGraphError("Prompt graph edges must be an array")
    node_ids = {node["id"] for node in nodes}
    final_targets = {"final_prompt"} | {node["id"] for node in nodes if node["type"] == "output"}
    allowed_targets = node_ids | final_targets
    normalized_edges: list[dict[str, str]] = []
    seen_edges: set[tuple[str, str]] = set()
    for index, edge in enumerate(value):
        if not isinstance(edge, dict):
            raise PromptGraphError(f"Prompt graph edge at index {index} must be an object")
        source = edge.get("source")
        target = edge.get("target")
        if not isinstance(source, str) or not source.strip():
            raise PromptGraphError(f"Prompt graph edge at index {index} source must be a non-empty string")
        if not isinstance(target, str) or not target.strip():
            raise PromptGraphError(f"Prompt graph edge at index {index} target must be a non-empty string")
        if source not in node_ids:
            raise PromptGraphError(f"Prompt graph edge source does not exist: {source}")
        if target not in allowed_targets:
            raise PromptGraphError(f"Prompt graph edge target does not exist: {target}")
        if source == target:
            raise PromptGraphError(f"Prompt graph edge creates a self cycle: {source}")
        edge_key = (source, target)
        if edge_key in seen_edges:
            raise PromptGraphError(f"Prompt graph contains duplicate edge: {source} -> {target}")
        seen_edges.add(edge_key)
        normalized_edges.append({"source": source, "target": target})

    _reject_edge_cycles(node_ids, normalized_edges)
    _validate_final_prompt_reachability(node_ids, final_targets, normalized_edges)
    return normalized_edges


def _reject_edge_cycles(node_ids: set[str], edges: list[dict[str, str]]) -> None:
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        target = edge["target"]
        if target in node_ids:
            adjacency[edge["source"]].append(target)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str, path: list[str]) -> None:
        if node_id in visiting:
            cycle = " -> ".join(path + [node_id])
            raise PromptGraphError(f"Prompt graph contains a cycle: {cycle}")
        if node_id in visited:
            return
        visiting.add(node_id)
        for target in adjacency[node_id]:
            visit(target, path + [node_id])
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in sorted(node_ids):
        visit(node_id, [])


def _validate_final_prompt_reachability(
    node_ids: set[str], final_targets: set[str], edges: list[dict[str, str]]
) -> None:
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for edge in edges:
        adjacency[edge["source"]].append(edge["target"])

    memo: dict[str, bool] = {}

    def reaches_final(node_id: str) -> bool:
        if node_id in final_targets:
            return True
        if node_id in memo:
            return memo[node_id]
        result = any(target in final_targets or (target in node_ids and reaches_final(target)) for target in adjacency[node_id])
        memo[node_id] = result
        return result

    unreachable = sorted(node_id for node_id in node_ids if not reaches_final(node_id))
    if unreachable:
        raise PromptGraphError(f"Prompt graph node(s) cannot reach final prompt: {', '.join(unreachable)}")


def _node(node_id: str, node_type: str, order: int, **extra: Any) -> dict[str, Any]:
    return {"id": node_id, "type": node_type, "order": order, **extra}


def _prompt_graph_path(scenario_id: str) -> str:
    return f"rp/scenarios/{scenario_id}/prompt_graph.json"


def _validate_scenario_id(scenario_id: str) -> None:
    if not is_locus_id(scenario_id):
        raise PromptGraphError(f"Invalid scenario id: {scenario_id}")

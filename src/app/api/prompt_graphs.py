from __future__ import annotations

from typing import Any
from app.api_validation import (
    ApiBadRequest,
    optional_query_id as _optional_query_id,
    query_string as _query_string,
    require_id as _require_id,
)
from app.loaders import load_scenario
from app.prompt_preview import build_prompt_preview
from app.prompt_graph import (
    prompt_graph_warnings,
    read_prompt_graph,
    read_start_prompt_graph,
    write_prompt_graph,
    write_start_prompt_graph,
)
from app.starts import StartError, create_start, list_starts, read_start_manifest, write_start_manifest
from app.vault import Vault
from app.api.common import ApiResponse, _error_response, _json_response


def _scenario_starts_response(vault: Vault, scenario_id: str) -> dict[str, Any]:
    load_scenario(vault, scenario_id)
    starts = []
    for info in list_starts(vault, scenario_id):
        manifest = read_start_manifest(vault, scenario_id, info.id)
        starts.append({
            "id": info.id,
            "name": info.name,
            "body": info.body,
            "has_manifest": info.has_manifest,
            "lore_include": manifest.lore_include,
            "lore_exclude": manifest.lore_exclude,
            "initial_state_path": manifest.initial_state_path,
        })
    return {"scenario_id": scenario_id, "starts": starts}


def _create_start_response(vault: Vault, scenario_id: str, payload: dict[str, Any]) -> ApiResponse:
    load_scenario(vault, scenario_id)
    starting_id = _require_id(payload, "id")
    name = payload.get("name", "")
    if not isinstance(name, str) or not name.strip():
        raise ApiBadRequest("name must be a non-empty string")
    body = payload.get("body", "")
    if not isinstance(body, str):
        raise ApiBadRequest("body must be a string")
    try:
        info = create_start(vault, scenario_id, starting_id, name.strip(), body)
    except StartError as exc:
        return _error_response(409, str(exc))
    return _json_response({"scenario_id": scenario_id, "start": {"id": info.id, "name": info.name, "body": info.body}}, status=201)


def _scenario_prompt_graph_response(vault: Vault, scenario_id: str) -> dict[str, Any]:
    graph = read_prompt_graph(vault, scenario_id)
    graph_path = vault.resolve(f"rp/scenarios/{scenario_id}/prompt_graph.json")
    return {
        "scenario_id": scenario_id,
        "source": "vault" if graph_path.is_file() else "default",
        "graph": graph,
        "warnings": prompt_graph_warnings(vault, scenario_id, graph),
    }


def _update_scenario_prompt_graph_response(vault: Vault, scenario_id: str, payload: dict[str, Any]) -> ApiResponse:
    graph = payload.get("graph", payload)
    if not isinstance(graph, dict):
        raise ApiBadRequest("prompt graph payload must be a JSON object")
    saved = write_prompt_graph(vault, scenario_id, graph)
    return _json_response(
        {
            "scenario_id": scenario_id,
            "source": "vault",
            "graph": saved,
            "warnings": prompt_graph_warnings(vault, scenario_id, saved),
        }
    )


def _start_prompt_graph_response(vault: Vault, scenario_id: str, starting_id: str) -> dict[str, Any]:
    result = read_start_prompt_graph(vault, scenario_id, starting_id)
    graph = result["graph"]
    return {
        "scenario_id": scenario_id,
        "starting_id": starting_id,
        "own_graph": result["own_graph"],
        "source": result["source"],
        "graph": graph,
        "warnings": prompt_graph_warnings(vault, scenario_id, graph),
    }


def _update_start_prompt_graph_response(vault: Vault, scenario_id: str, starting_id: str, payload: dict[str, Any]) -> ApiResponse:
    graph = payload.get("graph", payload)
    if not isinstance(graph, dict):
        raise ApiBadRequest("prompt graph payload must be a JSON object")
    saved = write_start_prompt_graph(vault, scenario_id, starting_id, graph)
    return _json_response(
        {
            "scenario_id": scenario_id,
            "starting_id": starting_id,
            "own_graph": True,
            "source": "start",
            "graph": saved,
            "warnings": prompt_graph_warnings(vault, scenario_id, saved),
        }
    )


def _start_manifest_response(vault: Vault, scenario_id: str, starting_id: str) -> dict[str, Any]:
    try:
        manifest = read_start_manifest(vault, scenario_id, starting_id)
    except StartError as exc:
        raise ApiBadRequest(str(exc)) from exc
    return {
        "scenario_id": scenario_id,
        "starting_id": starting_id,
        "manifest": {
            "name": manifest.name,
            "description": manifest.description,
            "lore_include": manifest.lore_include,
            "lore_exclude": manifest.lore_exclude,
            "initial_state_path": manifest.initial_state_path,
        },
    }


def _update_start_manifest_response(vault: Vault, scenario_id: str, starting_id: str, payload: dict[str, Any]) -> ApiResponse:
    name = payload.get("name", "")
    description = payload.get("description", "")
    lore_include = payload.get("lore_include", [])
    lore_exclude = payload.get("lore_exclude", [])
    initial_state_path = payload.get("initial_state_path") or None

    if not isinstance(lore_include, list):
        raise ApiBadRequest("lore_include must be a list")
    if not isinstance(lore_exclude, list):
        raise ApiBadRequest("lore_exclude must be a list")

    try:
        manifest = write_start_manifest(
            vault,
            scenario_id,
            starting_id,
            name=name,
            description=description,
            lore_include=lore_include,
            lore_exclude=lore_exclude,
            initial_state_path=initial_state_path,
        )
    except StartError as exc:
        raise ApiBadRequest(str(exc)) from exc
    return _json_response({
        "scenario_id": scenario_id,
        "starting_id": starting_id,
        "manifest": {
            "name": manifest.name,
            "description": manifest.description,
            "lore_include": manifest.lore_include,
            "lore_exclude": manifest.lore_exclude,
            "initial_state_path": manifest.initial_state_path,
        },
    })


def _scenario_prompt_preview_response(vault: Vault, scenario_id: str, query: dict[str, list[str]]) -> dict[str, Any]:
    session_id = _optional_query_id(query, "session_id")
    persona_id = _optional_query_id(query, "persona_id")
    profile_id = _optional_query_id(query, "profile_id")
    starting_id = _optional_query_id(query, "starting_id")
    user_message = _query_string(query, "user_message")
    user_note = _query_string(query, "user_note", required=False)
    session_note = _query_string(query, "session_note", required=False) if "session_note" in query else None
    scene_note = _query_string(query, "scene_note", required=False) if "scene_note" in query else None
    return build_prompt_preview(
        vault,
        scenario_id=scenario_id,
        session_id=session_id,
        persona_id=persona_id,
        profile_id=profile_id,
        starting_id=starting_id,
        user_message=user_message,
        user_note=user_note,
        session_note=session_note,
        scene_note=scene_note,
    )

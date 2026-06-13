from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse
from app.api_validation import (
    ApiBadRequest,
    decode_json_body as _decode_json_body,
    optional_query_id as _optional_query_id,
    require_id as _require_id,
    validate_id as _validate_id,
)
from app.images import ImageMarkerError
from app.loaders import load_scenario
from app.memory_consolidation import (
    MemoryConsolidationError,
    apply_consolidation_suggestion,
    list_consolidation_suggestions,
    run_memory_consolidation,
    update_consolidation_suggestion_status,
)
from app.model_client import ModelClientError
from app.scenario_settings import ScenarioSettingsError, read_scenario_settings, write_scenario_settings
from app.starts import StartError, delete_start
from app.state_session import delete_session, read_current_state, read_session_state
from app.turn_loop import ChatCompletionClient
from app.vault import Vault, VaultError
from app.api.assets import _image_response
from app.api.common import ApiNotFound, ApiResponse, ApiStreamResponse, _error_response, _json_response
from app.api.personas_profiles import (
    _create_persona,
    _persona_detail,
    _persona_summaries,
    _profile_detail,
    _profile_summaries,
    _update_persona,
    _update_profile,
)
from app.api.prompt_graphs import (
    _create_start_response,
    _scenario_prompt_graph_response,
    _scenario_prompt_preview_response,
    _scenario_starts_response,
    _start_manifest_response,
    _start_prompt_graph_response,
    _update_scenario_prompt_graph_response,
    _update_start_manifest_response,
    _update_start_prompt_graph_response,
)
from app.api.rag_memory import (
    _ALLOWED_MEMORY_KINDS,
    _scenario_memory_response,
    _scenario_rag_rebuild_response,
    _scenario_rag_rebuild_vectors_response,
    _scenario_rag_status,
    _scenario_rag_vector_status,
    _update_memory_metadata_response,
)
from app.api.scenarios import (
    _create_scenario_response,
    _create_scenario_source_file,
    _delete_scenario_source_file,
    _scenario_character_bustups_response,
    _scenario_export_response,
    _scenario_import_response,
    _scenario_source_file,
    _scenario_source_files,
    _scenario_startings_response,
    _scenario_state_template,
    _scenario_summaries,
    _update_scenario_source_file,
)
from app.api.sessions import (
    _create_branch_session_response,
    _create_session_response,
    _session_detail_response,
    _session_latest_prompt_response,
    _session_log_response,
    _session_pins_response,
    _session_summaries,
    _session_timeline_response,
    _update_session_pins_response,
    _update_session_settings_response,
    _update_session_starting_response,
)
from app.api.turns import (
    _continue_session_message_response,
    _delete_session_message_response,
    _postprocess_job_response,
    _regenerate_session_message_response,
    _turn_job_response,
    _turn_response,
    _update_session_message_candidate_response,
    _update_session_message_response,
)


def handle_get(path: str, vault: Vault) -> ApiResponse:
    route, query = _parse_api_request(path)
    if not route or route[0] != "api":
        raise ApiNotFound()

    try:
        for handler in (
            _handle_core_get,
            _handle_persona_profile_get,
            _handle_scenario_content_get,
            _handle_rag_memory_get,
            _handle_session_get,
            _handle_asset_get,
        ):
            response = handler(route, query, vault)
            if response is not None:
                return response
    except (VaultError, ImageMarkerError) as exc:
        return _json_response({"error": type(exc).__name__, "message": str(exc)}, status=400)

    raise ApiNotFound()


def handle_post(
    path: str,
    body: bytes,
    vault: Vault,
    *,
    model_client: ChatCompletionClient | None = None,
    state_model_client: ChatCompletionClient | None = None,
) -> ApiResponse | ApiStreamResponse:
    route, query = _parse_api_request(path)
    if not route or route[0] != "api":
        raise ApiNotFound()

    # Import endpoint receives raw ZIP bytes — skip JSON decode
    if route == ["api", "scenarios", "import"]:
        try:
            return _scenario_import_response(vault, body, query)
        except (VaultError, ApiBadRequest) as exc:
            return _json_response({"error": type(exc).__name__, "message": str(exc)}, status=400)

    try:
        payload = _decode_json_body(body)
        for handler in (
            _handle_core_post,
            _handle_scenario_content_post,
            _handle_rag_memory_post,
            _handle_session_post,
        ):
            response = handler(route, vault, payload, model_client=model_client, state_model_client=state_model_client)
            if response is not None:
                return response
    except (VaultError, ImageMarkerError, ApiBadRequest) as exc:
        return _json_response({"error": type(exc).__name__, "message": str(exc)}, status=400)
    except ModelClientError as exc:
        return _json_response({"error": type(exc).__name__, "message": str(exc)}, status=502)

    raise ApiNotFound()


def handle_put(path: str, body: bytes, vault: Vault) -> ApiResponse:
    route, _query = _parse_api_request(path)
    if not route or route[0] != "api":
        raise ApiNotFound()

    try:
        payload = _decode_json_body(body)
        for handler in (
            _handle_persona_profile_put,
            _handle_scenario_content_put,
            _handle_rag_memory_put,
            _handle_session_put,
        ):
            response = handler(route, vault, payload)
            if response is not None:
                return response
    except (VaultError, ImageMarkerError, ApiBadRequest) as exc:
        return _json_response({"error": type(exc).__name__, "message": str(exc)}, status=400)

    raise ApiNotFound()


def handle_delete(path: str, vault: Vault) -> ApiResponse:
    route, query = _parse_api_request(path)
    if not route or route[0] != "api":
        raise ApiNotFound()

    try:
        for handler in (_handle_scenario_content_delete, _handle_rag_memory_delete, _handle_session_delete):
            response = handler(route, query, vault)
            if response is not None:
                return response
    except (VaultError, ImageMarkerError, ApiBadRequest) as exc:
        return _json_response({"error": type(exc).__name__, "message": str(exc)}, status=400)

    raise ApiNotFound()


def _parse_api_request(path: str) -> tuple[list[str], dict[str, list[str]]]:
    parsed = urlparse(path)
    route = [unquote(part) for part in parsed.path.split("/") if part]
    return route, parse_qs(parsed.query)


def _handle_core_get(route: list[str], _query: dict[str, list[str]], vault: Vault) -> ApiResponse | None:
    if route == ["api", "health"]:
        return _json_response(_health_response(vault))
    if route == ["api", "scenarios"]:
        return _json_response({"scenarios": _scenario_summaries(vault)})
    return None


def _handle_persona_profile_get(route: list[str], _query: dict[str, list[str]], vault: Vault) -> ApiResponse | None:
    if route == ["api", "personas"]:
        return _json_response({"personas": _persona_summaries(vault)})
    if len(route) == 3 and route[:2] == ["api", "personas"]:
        persona_id = _validate_id(route[2], "persona")
        return _json_response(_persona_detail(vault, persona_id))
    if route == ["api", "profiles"]:
        return _json_response({"profiles": _profile_summaries(vault)})
    if len(route) == 3 and route[:2] == ["api", "profiles"]:
        profile_id = _validate_id(route[2], "profile")
        return _json_response(_profile_detail(vault, profile_id))
    return None


def _handle_scenario_content_get(route: list[str], query: dict[str, list[str]], vault: Vault) -> ApiResponse | None:
    if len(route) == 4 and route[:2] == ["api", "scenarios"] and route[3] == "export":
        scenario_id = _validate_id(route[2], "scenario")
        return _scenario_export_response(vault, scenario_id)
    if len(route) == 4 and route[:2] == ["api", "scenarios"] and route[3] == "source":
        scenario_id = _validate_id(route[2], "scenario")
        source_path = query.get("path", [""])[0]
        if source_path:
            return _json_response(_scenario_source_file(vault, scenario_id, source_path))
        return _json_response({"scenario_id": scenario_id, "files": _scenario_source_files(vault, scenario_id)})
    if len(route) == 4 and route[:2] == ["api", "scenarios"] and route[3] == "startings":
        scenario_id = _validate_id(route[2], "scenario")
        return _json_response(_scenario_startings_response(vault, scenario_id))
    if len(route) == 4 and route[:2] == ["api", "scenarios"] and route[3] == "character-bustups":
        scenario_id = _validate_id(route[2], "scenario")
        return _json_response(_scenario_character_bustups_response(vault, scenario_id))
    if len(route) == 4 and route[:2] == ["api", "scenarios"] and route[3] == "prompt-graph":
        scenario_id = _validate_id(route[2], "scenario")
        return _json_response(_scenario_prompt_graph_response(vault, scenario_id))
    if len(route) == 4 and route[:2] == ["api", "scenarios"] and route[3] == "settings":
        scenario_id = _validate_id(route[2], "scenario")
        return _json_response({"scenario_id": scenario_id, "settings": read_scenario_settings(vault, scenario_id)})
    if len(route) == 4 and route[:2] == ["api", "scenarios"] and route[3] == "starts":
        scenario_id = _validate_id(route[2], "scenario")
        return _json_response(_scenario_starts_response(vault, scenario_id))
    if len(route) == 6 and route[:2] == ["api", "scenarios"] and route[3] == "starts" and route[5] == "prompt-graph":
        scenario_id = _validate_id(route[2], "scenario")
        starting_id = _validate_id(route[4], "start")
        return _json_response(_start_prompt_graph_response(vault, scenario_id, starting_id))
    if len(route) == 6 and route[:2] == ["api", "scenarios"] and route[3] == "starts" and route[5] == "manifest":
        scenario_id = _validate_id(route[2], "scenario")
        starting_id = _validate_id(route[4], "start")
        return _json_response(_start_manifest_response(vault, scenario_id, starting_id))
    if len(route) == 4 and route[:2] == ["api", "scenarios"] and route[3] == "prompt-preview":
        scenario_id = _validate_id(route[2], "scenario")
        return _json_response(_scenario_prompt_preview_response(vault, scenario_id, query))
    if len(route) == 4 and route[:2] == ["api", "scenarios"] and route[3] == "state":
        scenario_id = _validate_id(route[2], "scenario")
        return _json_response(
            {"scenario_id": scenario_id, "state": read_current_state(vault, scenario_id), "state_scope": "initial"}
        )
    if len(route) == 5 and route[:2] == ["api", "scenarios"] and route[3:5] == ["state", "template"]:
        scenario_id = _validate_id(route[2], "scenario")
        return _json_response(_scenario_state_template(vault, scenario_id))
    return None


def _handle_rag_memory_get(route: list[str], query: dict[str, list[str]], vault: Vault) -> ApiResponse | None:
    if len(route) == 5 and route[:2] == ["api", "scenarios"] and route[3:5] == ["rag", "status"]:
        scenario_id = _validate_id(route[2], "scenario")
        return _json_response(_scenario_rag_status(vault, scenario_id))
    if len(route) == 5 and route[:2] == ["api", "scenarios"] and route[3:5] == ["rag", "vector-status"]:
        scenario_id = _validate_id(route[2], "scenario")
        return _json_response(_scenario_rag_vector_status(vault, scenario_id))
    if len(route) == 4 and route[:2] == ["api", "scenarios"] and route[3] == "memory":
        scenario_id = _validate_id(route[2], "scenario")
        return _json_response(_scenario_memory_response(vault, scenario_id, session_id=_optional_query_id(query, "session_id")))
    if len(route) == 5 and route[:2] == ["api", "scenarios"] and route[3:5] == ["memory", "consolidation-suggestions"]:
        scenario_id = _validate_id(route[2], "scenario")
        try:
            suggestions = list_consolidation_suggestions(vault, scenario_id)
        except MemoryConsolidationError as exc:
            raise ApiBadRequest(str(exc)) from exc
        return _json_response({"scenario_id": scenario_id, "suggestions": suggestions, "total": len(suggestions)})
    return None


def _handle_session_get(route: list[str], query: dict[str, list[str]], vault: Vault) -> ApiResponse | None:
    if len(route) == 4 and route[:2] == ["api", "scenarios"] and route[3] == "sessions":
        scenario_id = _validate_id(route[2], "scenario")
        return _json_response({"scenario_id": scenario_id, "sessions": _session_summaries(vault, scenario_id)})
    if len(route) == 5 and route[:2] == ["api", "scenarios"] and route[3] == "sessions":
        scenario_id = _validate_id(route[2], "scenario")
        session_id = _validate_id(route[4], "session")
        return _json_response(_session_detail_response(vault, scenario_id, session_id))
    if len(route) == 6 and route[:2] == ["api", "scenarios"] and route[3] == "sessions" and route[5] == "state":
        scenario_id = _validate_id(route[2], "scenario")
        session_id = _validate_id(route[4], "session")
        return _json_response(
            {
                "scenario_id": scenario_id,
                "session_id": session_id,
                "state": read_session_state(vault, scenario_id, session_id),
                "state_scope": "session",
            }
        )
    if len(route) == 6 and route[:2] == ["api", "scenarios"] and route[3] == "sessions" and route[5] == "pins":
        scenario_id = _validate_id(route[2], "scenario")
        session_id = _validate_id(route[4], "session")
        return _json_response(_session_pins_response(vault, scenario_id, session_id))
    if len(route) == 6 and route[:2] == ["api", "scenarios"] and route[3] == "sessions" and route[5] == "timeline":
        scenario_id = _validate_id(route[2], "scenario")
        session_id = _validate_id(route[4], "session")
        return _json_response(_session_timeline_response(vault, scenario_id, session_id))
    if len(route) == 6 and route[:2] == ["api", "scenarios"] and route[3] == "sessions" and route[5] == "log":
        scenario_id = _validate_id(route[2], "scenario")
        session_id = _validate_id(route[4], "session")
        return _json_response(_session_log_response(vault, scenario_id, session_id, query))
    if len(route) == 7 and route[:2] == ["api", "scenarios"] and route[3] == "sessions" and route[5:7] == ["prompt", "latest"]:
        scenario_id = _validate_id(route[2], "scenario")
        session_id = _validate_id(route[4], "session")
        return _json_response(_session_latest_prompt_response(vault, scenario_id, session_id))
    if len(route) == 7 and route[:2] == ["api", "scenarios"] and route[3] == "sessions" and route[5] == "turns":
        scenario_id = _validate_id(route[2], "scenario")
        session_id = _validate_id(route[4], "session")
        turn_id = _validate_id(route[6], "turn")
        return _json_response(_turn_job_response(vault, scenario_id, session_id, turn_id))
    if len(route) == 7 and route[:2] == ["api", "scenarios"] and route[3] == "sessions" and route[5] == "postprocess":
        scenario_id = _validate_id(route[2], "scenario")
        session_id = _validate_id(route[4], "session")
        job_id = _validate_id(route[6], "postprocess")
        return _json_response(_postprocess_job_response(vault, scenario_id, session_id, job_id))
    return None


def _handle_asset_get(route: list[str], _query: dict[str, list[str]], vault: Vault) -> ApiResponse | None:
    if len(route) == 6 and route[:3] == ["api", "assets", "images"]:
        return _image_response(vault, route[3], route[4], route[5])
    return None


def _handle_core_post(
    route: list[str],
    vault: Vault,
    payload: dict[str, Any],
    **_clients: Any,
) -> ApiResponse | ApiStreamResponse | None:
    if route == ["api", "scenarios"]:
        return _json_response(_create_scenario_response(vault, payload), status=201)
    if route == ["api", "personas"]:
        return _json_response(_create_persona(vault, payload), status=201)
    if route == ["api", "sessions"]:
        return _create_session_response(vault, payload)
    return None


def _handle_scenario_content_post(
    route: list[str],
    vault: Vault,
    payload: dict[str, Any],
    **_clients: Any,
) -> ApiResponse | ApiStreamResponse | None:
    if len(route) == 4 and route[:2] == ["api", "scenarios"] and route[3] == "source":
        scenario_id = _validate_id(route[2], "scenario")
        return _json_response(_create_scenario_source_file(vault, scenario_id, payload), status=201)
    if len(route) == 4 and route[:2] == ["api", "scenarios"] and route[3] == "starts":
        scenario_id = _validate_id(route[2], "scenario")
        return _create_start_response(vault, scenario_id, payload)
    return None


def _handle_rag_memory_post(
    route: list[str],
    vault: Vault,
    payload: dict[str, Any],
    *,
    state_model_client: ChatCompletionClient | None = None,
    **_clients: Any,
) -> ApiResponse | ApiStreamResponse | None:
    if len(route) == 5 and route[:2] == ["api", "scenarios"] and route[3:5] == ["rag", "rebuild"]:
        scenario_id = _validate_id(route[2], "scenario")
        return _json_response(_scenario_rag_rebuild_response(vault, scenario_id))
    if len(route) == 5 and route[:2] == ["api", "scenarios"] and route[3:5] == ["rag", "rebuild-vectors"]:
        scenario_id = _validate_id(route[2], "scenario")
        return _json_response(_scenario_rag_rebuild_vectors_response(vault, scenario_id))
    if len(route) == 5 and route[:2] == ["api", "scenarios"] and route[3:5] == ["memory", "consolidation-suggestions"]:
        scenario_id = _validate_id(route[2], "scenario")
        session_id = _require_id(payload, "session_id")
        profile_id = _require_id(payload, "profile_id")
        if state_model_client is None:
            raise ApiBadRequest("state_model_client is required for memory consolidation")
        try:
            result = run_memory_consolidation(
                vault,
                scenario_id=scenario_id,
                session_id=session_id,
                profile_id=profile_id,
                model_client=state_model_client,
            )
        except MemoryConsolidationError as exc:
            raise ApiBadRequest(str(exc)) from exc
        return _json_response(
            {
                "scenario_id": scenario_id,
                "session_id": session_id,
                "created_files": result.created_files,
                "suggestions": result.suggestions,
            },
            status=201,
        )
    return None


def _handle_session_post(
    route: list[str],
    vault: Vault,
    payload: dict[str, Any],
    *,
    model_client: ChatCompletionClient | None = None,
    state_model_client: ChatCompletionClient | None = None,
) -> ApiResponse | ApiStreamResponse | None:
    if len(route) == 6 and route[:2] == ["api", "scenarios"] and route[3] == "sessions" and route[5] == "branches":
        scenario_id = _validate_id(route[2], "scenario")
        session_id = _validate_id(route[4], "session")
        return _create_branch_session_response(vault, scenario_id, session_id, payload)
    if len(route) == 6 and route[:2] == ["api", "scenarios"] and route[3] == "sessions" and route[5] == "settings":
        scenario_id = _validate_id(route[2], "scenario")
        session_id = _validate_id(route[4], "session")
        return _update_session_settings_response(vault, scenario_id, session_id, payload)
    if len(route) == 6 and route[:2] == ["api", "scenarios"] and route[3] == "sessions" and route[5] == "turns":
        scenario_id = _validate_id(route[2], "scenario")
        session_id = _validate_id(route[4], "session")
        return _turn_response(
            vault,
            scenario_id,
            session_id,
            payload,
            model_client=model_client,
            state_model_client=state_model_client,
        )
    if len(route) == 8 and route[:2] == ["api", "scenarios"] and route[3] == "sessions" and route[5] == "messages" and route[7] == "regenerate":
        scenario_id = _validate_id(route[2], "scenario")
        session_id = _validate_id(route[4], "session")
        turn = int(route[6])
        return _regenerate_session_message_response(
            vault,
            scenario_id,
            session_id,
            turn,
            payload,
            model_client=model_client,
            state_model_client=state_model_client,
        )
    if len(route) == 8 and route[:2] == ["api", "scenarios"] and route[3] == "sessions" and route[5] == "messages" and route[7] == "continue":
        scenario_id = _validate_id(route[2], "scenario")
        session_id = _validate_id(route[4], "session")
        turn = int(route[6])
        return _continue_session_message_response(
            vault,
            scenario_id,
            session_id,
            turn,
            payload,
            model_client=model_client,
        )
    return None


def _handle_persona_profile_put(route: list[str], vault: Vault, payload: dict[str, Any]) -> ApiResponse | None:
    if len(route) == 3 and route[:2] == ["api", "personas"]:
        persona_id = _validate_id(route[2], "persona")
        return _json_response(_update_persona(vault, persona_id, payload))
    if len(route) == 3 and route[:2] == ["api", "profiles"]:
        profile_id = _validate_id(route[2], "profile")
        return _json_response(_update_profile(vault, profile_id, payload))
    return None


def _handle_scenario_content_put(route: list[str], vault: Vault, payload: dict[str, Any]) -> ApiResponse | None:
    if len(route) == 4 and route[:2] == ["api", "scenarios"] and route[3] == "source":
        scenario_id = _validate_id(route[2], "scenario")
        return _json_response(_update_scenario_source_file(vault, scenario_id, payload))
    if len(route) == 4 and route[:2] == ["api", "scenarios"] and route[3] == "prompt-graph":
        scenario_id = _validate_id(route[2], "scenario")
        return _update_scenario_prompt_graph_response(vault, scenario_id, payload)
    if len(route) == 4 and route[:2] == ["api", "scenarios"] and route[3] == "settings":
        scenario_id = _validate_id(route[2], "scenario")
        try:
            saved = write_scenario_settings(vault, scenario_id, payload)
        except ScenarioSettingsError as exc:
            return _error_response(400, str(exc))
        return _json_response({"scenario_id": scenario_id, "settings": saved})
    if len(route) == 6 and route[:2] == ["api", "scenarios"] and route[3] == "starts" and route[5] == "prompt-graph":
        scenario_id = _validate_id(route[2], "scenario")
        starting_id = _validate_id(route[4], "start")
        return _update_start_prompt_graph_response(vault, scenario_id, starting_id, payload)
    if len(route) == 6 and route[:2] == ["api", "scenarios"] and route[3] == "starts" and route[5] == "manifest":
        scenario_id = _validate_id(route[2], "scenario")
        starting_id = _validate_id(route[4], "start")
        return _update_start_manifest_response(vault, scenario_id, starting_id, payload)
    return None


def _handle_session_put(route: list[str], vault: Vault, payload: dict[str, Any]) -> ApiResponse | None:
    if len(route) == 8 and route[:2] == ["api", "scenarios"] and route[3] == "sessions" and route[5] == "messages":
        scenario_id = _validate_id(route[2], "scenario")
        session_id = _validate_id(route[4], "session")
        turn = int(route[6])
        role = route[7]
        return _json_response(_update_session_message_response(vault, scenario_id, session_id, turn, role, payload))
    if len(route) == 9 and route[:2] == ["api", "scenarios"] and route[3] == "sessions" and route[5] == "messages" and route[7:9] == ["assistant", "candidate"]:
        scenario_id = _validate_id(route[2], "scenario")
        session_id = _validate_id(route[4], "session")
        turn = int(route[6])
        return _json_response(_update_session_message_candidate_response(vault, scenario_id, session_id, turn, payload))
    if len(route) == 6 and route[:2] == ["api", "scenarios"] and route[3] == "sessions" and route[5] == "pins":
        scenario_id = _validate_id(route[2], "scenario")
        session_id = _validate_id(route[4], "session")
        return _json_response(_update_session_pins_response(vault, scenario_id, session_id, payload))
    if len(route) == 6 and route[:2] == ["api", "scenarios"] and route[3] == "sessions" and route[5] == "starting":
        scenario_id = _validate_id(route[2], "scenario")
        session_id = _validate_id(route[4], "session")
        return _json_response(_update_session_starting_response(vault, scenario_id, session_id, payload))
    return None


def _handle_scenario_content_delete(route: list[str], query: dict[str, list[str]], vault: Vault) -> ApiResponse | None:
    if len(route) == 4 and route[:2] == ["api", "scenarios"] and route[3] == "source":
        scenario_id = _validate_id(route[2], "scenario")
        return _json_response(_delete_scenario_source_file(vault, scenario_id, query))
    if len(route) == 5 and route[:2] == ["api", "scenarios"] and route[3] == "starts":
        scenario_id = _validate_id(route[2], "scenario")
        starting_id = _validate_id(route[4], "start")
        try:
            delete_start(vault, scenario_id, starting_id)
        except StartError as exc:
            return _error_response(404, str(exc))
        return _json_response({"scenario_id": scenario_id, "starting_id": starting_id, "deleted": True})
    return None


def _handle_rag_memory_put(route: list[str], vault: Vault, payload: dict[str, Any]) -> ApiResponse | None:
    # PUT /api/scenarios/{id}/memory/consolidation-suggestions/{suggestion_id}
    if len(route) == 6 and route[:2] == ["api", "scenarios"] and route[3:5] == ["memory", "consolidation-suggestions"]:
        scenario_id = _validate_id(route[2], "scenario")
        suggestion_id = route[5]
        try:
            if payload.get("apply") is True:
                result = apply_consolidation_suggestion(vault, scenario_id=scenario_id, suggestion_id=suggestion_id)
                return _json_response(
                    {
                        "scenario_id": scenario_id,
                        "suggestion": result.suggestion,
                        "updated_memory_paths": result.updated_memory_paths,
                        "stale_paths": result.stale_paths,
                        "applied": True,
                    }
                )
            status = payload.get("status")
            if not isinstance(status, str):
                raise ApiBadRequest("status must be a string or apply must be true")
            suggestion = update_consolidation_suggestion_status(
                vault,
                scenario_id=scenario_id,
                suggestion_id=suggestion_id,
                status=status,
            )
        except MemoryConsolidationError as exc:
            raise ApiBadRequest(str(exc)) from exc
        return _json_response({"scenario_id": scenario_id, "suggestion": suggestion, "saved": True})
    # PUT /api/scenarios/{id}/memory/{kind}/{memory_id}
    if len(route) == 6 and route[:2] == ["api", "scenarios"] and route[3] == "memory":
        scenario_id = _validate_id(route[2], "scenario")
        kind = route[4]
        memory_id = route[5]
        return _json_response(_update_memory_metadata_response(vault, scenario_id, kind, memory_id, payload))
    return None


def _handle_rag_memory_delete(route: list[str], _query: dict[str, list[str]], vault: Vault) -> ApiResponse | None:
    # DELETE /api/scenarios/{id}/memory/{kind}/{memory_id}
    if len(route) == 6 and route[:2] == ["api", "scenarios"] and route[3] == "memory":
        scenario_id = _validate_id(route[2], "scenario")
        kind = route[4]
        memory_id = route[5]
        if kind not in _ALLOWED_MEMORY_KINDS:
            raise ApiBadRequest(f"Unknown memory kind: {kind!r}")
        if not re.match(r'^[A-Za-z0-9_-]+$', memory_id):
            raise ApiBadRequest(f"Invalid memory_id: {memory_id!r}")
        load_scenario(vault, scenario_id)
        mem_path = vault.resolve(f"rp/scenarios/{scenario_id}/memory/{kind}/{memory_id}.md")
        if not mem_path.is_file():
            return _json_response({"error": "not_found", "message": f"Memory not found: {kind}/{memory_id}"}, status=404)
        mem_path.unlink()
        from app.memory_summarizer import mark_rag_index_stale
        mark_rag_index_stale(vault, scenario_id, [])
        return _json_response({
            "scenario_id": scenario_id,
            "kind": kind,
            "memory_id": memory_id,
            "path": f"memory/{kind}/{memory_id}.md",
            "deleted": True,
        })
    return None


def _handle_session_delete(route: list[str], query: dict[str, list[str]], vault: Vault) -> ApiResponse | None:
    if len(route) == 5 and route[:2] == ["api", "scenarios"] and route[3] == "sessions":
        scenario_id = _validate_id(route[2], "scenario")
        session_id = _validate_id(route[4], "session")
        delete_session(vault, scenario_id, session_id)
        return _json_response({"scenario_id": scenario_id, "session_id": session_id, "deleted": True})
    if len(route) == 8 and route[:2] == ["api", "scenarios"] and route[3] == "sessions" and route[5] == "messages":
        scenario_id = _validate_id(route[2], "scenario")
        session_id = _validate_id(route[4], "session")
        turn = int(route[6])
        role = route[7]
        return _json_response(_delete_session_message_response(vault, scenario_id, session_id, turn, role, query))
    return None


_VAULT_REQUIRED_DIRS = ("rp/scenarios", "rp/personas", "rp/profiles")


def _health_response(vault: Vault) -> dict[str, Any]:
    try:
        vault_accessible = vault.root.is_dir()
    except Exception:
        vault_accessible = False

    dirs: dict[str, bool] = {}
    for rel in _VAULT_REQUIRED_DIRS:
        try:
            dirs[rel] = vault.resolve(rel).is_dir()
        except Exception:
            dirs[rel] = False

    return {
        "backend": "ok",
        "vault": {
            "accessible": vault_accessible,
            "root": str(vault.root),
            "dirs": dirs,
        },
    }

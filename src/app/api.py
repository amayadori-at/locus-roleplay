from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, cast
from urllib.parse import parse_qs, unquote, urlparse

from app.api_validation import (
    ApiBadRequest,
    decode_json_body as _decode_json_body,
    is_allowed_scenario_source_path as _is_allowed_scenario_source_path,
    optional_id as _optional_id,
    optional_metadata_id as _optional_metadata_id,
    optional_non_negative_int_query as _optional_non_negative_int_query,
    optional_positive_int_query as _optional_positive_int_query,
    optional_query_id as _optional_query_id,
    query_string as _query_string,
    require_id as _require_id,
    require_metadata_id as _require_metadata_id,
    require_string_payload as _require_string_payload,
    validate_deletable_scenario_source_path as _validate_deletable_scenario_source_path,
    validate_id as _validate_id,
    validate_new_scenario_source_path as _validate_new_scenario_source_path,
    validate_scenario_source_path as _validate_scenario_source_path,
)
from app.images import ALLOWED_IMAGE_EXTENSIONS, ImageMarkerError, image_asset_path, image_asset_url, parse_image_markers
from app.ids import is_locus_id
from app.loaders import (
    SECRET_PROFILE_FIELDS,
    LoaderError,
    list_personas,
    list_profiles,
    list_scenarios,
    list_startings,
    load_persona,
    load_profile,
    load_scenario,
    load_starting,
)
from app.memory_consolidation import (
    MemoryConsolidationError,
    apply_consolidation_suggestion,
    list_consolidation_suggestions,
    run_memory_consolidation,
    update_consolidation_suggestion_status,
)
from app.model_client import ModelClientError, OpenAICompatibleClient
from app.postprocess_jobs import find_active_postprocess_job, read_postprocess_job, start_postprocess_job
from app.prompt_preview import build_prompt_preview
from app.prompt_graph import (
    has_start_prompt_graph,
    prompt_graph_warnings,
    read_prompt_graph,
    read_start_prompt_graph,
    write_prompt_graph,
    write_start_prompt_graph,
)
from app.scenario_settings import ScenarioSettingsError, read_scenario_settings, write_scenario_settings
from app.starts import StartError, create_start, delete_start, list_starts, read_start_manifest, resolve_initial_state_path, write_start_manifest
from app.embedding import EmbeddingError, get_embedding_config
from app.rag import (
    build_vector_index,
    list_available_characters,
    list_available_mods,
    load_scenario_file,
    rag_index_rebuild_needed,
    read_rag_index,
    read_vector_index,
    rebuild_rag_index,
    vector_index_rebuild_needed,
)
from app.state_session import (
    SessionMetadata,
    append_session_log,
    copy_session_state_for_turn,
    create_session,
    delete_session,
    list_session_metadata,
    next_session_id,
    read_current_state,
    read_session_candidate_state,
    read_latest_session_prompt,
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
    finalize_gm_turn,
    finalize_gm_turn_fast,
    prepare_gm_turn,
    run_gm_turn,
)
from app.reasoning import remove_reasoning_blocks as _remove_reasoning_blocks
from app.reasoning import strip_reasoning_blocks as _strip_reasoning_blocks
from app.turn_prompt_payload import latest_prompt_payload
from app.turn_payloads import segment_payload, turn_result_payload
from app.turn_jobs import find_active_turn_job, read_turn_job, start_turn_job
from app.vault import FrontmatterError, Vault, VaultError, VaultFileError, parse_markdown


@dataclass(frozen=True)
class ApiResponse:
    status: int
    content_type: str
    body: bytes
    last_modified: float | None = None
    headers: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class _RegenerateTargetContext:
    target_entry: dict[str, Any]
    user_message: str
    recent_log: list[dict[str, Any]]
    state_before_turn: dict[str, Any]
    state_source: dict[str, Any]


@dataclass(frozen=True)
class ApiStreamResponse:
    status: int
    content_type: str
    events: Iterable[bytes]


class ApiNotFound(Exception):
    pass


PROFILE_EDITABLE_FIELDS: frozenset[str] = frozenset({
    "model", "temperature", "top_p", "top_k", "context_size", "max_tokens",
    "frequency_penalty", "presence_penalty", "repetition_penalty", "reasoning_effort",
})

# Fields stripped from profile API responses — never sent to the frontend.
HIDDEN_PROFILE_RESPONSE_FIELDS: frozenset[str] = frozenset({
    "api_key_env",
    "endpoint_env",
})


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


_ALLOWED_MEMORY_KINDS: frozenset[str] = frozenset({"session_summaries", "extracted_facts", "unresolved_threads"})
_ALLOWED_MEMORY_STATUSES: frozenset[str] = frozenset({"active", "resolved", "superseded", "stale", "archived"})


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


def _update_memory_metadata_response(
    vault: Vault,
    scenario_id: str,
    kind: str,
    memory_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if kind not in _ALLOWED_MEMORY_KINDS:
        raise ApiBadRequest(f"Unknown memory kind: {kind!r}")
    if not re.match(r'^[A-Za-z0-9_-]+$', memory_id):
        raise ApiBadRequest(f"Invalid memory_id: {memory_id!r}")
    load_scenario(vault, scenario_id)
    scenario_relative = f"memory/{kind}/{memory_id}.md"
    vault_relative = f"rp/scenarios/{scenario_id}/{scenario_relative}"
    path = vault.resolve(vault_relative)
    if not path.is_file():
        raise ApiBadRequest(f"Memory not found: {kind}/{memory_id}")

    try:
        document = vault.load_markdown(vault_relative)
    except VaultFileError as exc:
        raise ApiBadRequest(f"memory markdown is unreadable: {scenario_relative}") from exc

    metadata = dict(document.frontmatter)
    changed = False
    if "rag_enabled" in payload:
        rag_enabled = payload.get("rag_enabled")
        if not isinstance(rag_enabled, bool):
            raise ApiBadRequest("rag_enabled must be a boolean")
        if rag_enabled:
            if metadata.pop("rag", None) is not None:
                changed = True
        elif metadata.get("rag") is not False:
            metadata["rag"] = False
            changed = True
    if "status" in payload:
        status = payload.get("status")
        if not isinstance(status, str) or status not in _ALLOWED_MEMORY_STATUSES:
            raise ApiBadRequest(f"Invalid memory status: {status!r}")
        if metadata.get("status") != status:
            metadata["status"] = status
            if status == "resolved" and not metadata.get("resolved_at"):
                metadata["resolved_at"] = _utc_timestamp()
            changed = True

    if changed:
        _atomic_write_text(path, _markdown_with_frontmatter(metadata, document.body))
        from app.memory_summarizer import mark_rag_index_stale
        mark_rag_index_stale(vault, scenario_id, [scenario_relative])

    normalized = _normalize_memory_metadata(metadata)
    return {
        "scenario_id": scenario_id,
        "kind": kind,
        "memory_id": memory_id,
        "path": scenario_relative,
        "metadata": normalized,
        "rag_enabled": normalized.get("rag") is not False,
        "status": normalized["status"],
        "saved": changed,
    }


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


def _scenario_summaries(vault: Vault) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for scenario_id in list_scenarios(vault):
        document = vault.load_markdown(f"rp/scenarios/{scenario_id}/scenario.md")
        metadata = dict(document.frontmatter)
        summaries.append(
            {
                "id": scenario_id,
                "name": metadata.get("name", scenario_id),
                "metadata": metadata,
                "description": document.body.strip(),
            }
        )
    return summaries


def _create_scenario_response(vault: Vault, payload: dict[str, Any]) -> dict[str, Any]:
    scenario_id = _validate_id(_require_string_payload(payload, "scenario_id"), "scenario")
    name = _require_string_payload(payload, "name")
    description = payload.get("description", "")
    if not isinstance(description, str):
        raise ApiBadRequest("description must be a string")
    scenario_dir = vault.resolve(f"rp/scenarios/{scenario_id}")
    if scenario_dir.exists():
        raise ApiBadRequest("scenario already exists")

    files = _scenario_template_files(scenario_id, name, description)
    directories = [
        "state",
        "gm",
        "characters",
        "lore",
        "memory/session_summaries",
        "memory/extracted_facts",
        "memory/unresolved_threads",
        "assets/images",
        "sessions",
        "startings",
    ]
    created_paths: list[str] = []
    try:
        scenario_dir.mkdir(parents=True)
        for directory in directories:
            (scenario_dir / directory).mkdir(parents=True, exist_ok=True)
        for relative_path, content in files.items():
            path = scenario_dir / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            created_paths.append(relative_path)
    except Exception:
        if scenario_dir.exists():
            import shutil

            shutil.rmtree(scenario_dir)
        raise

    scenario = load_scenario(vault, scenario_id)
    return {
        "scenario": {
            "id": scenario.id,
            "name": scenario.name,
            "metadata": scenario.metadata,
            "description": scenario.body.strip(),
        },
        "created": True,
        "created_files": created_paths,
    }


def _scenario_template_files(scenario_id: str, name: str, description: str) -> dict[str, str]:
    body = description.strip() or "このシナリオの説明をここに記述します。"
    return {
        "scenario.md": (
            "---\n"
            "type: scenario\n"
            f"id: {scenario_id}\n"
            f"name: {name}\n"
            "image_enabled: false\n"
            "image_mode: none\n"
            "memory_update_interval_turns: 4\n"
            "rag_scope:\n"
            "  - memory\n"
            "  - lore\n"
            "  - characters\n"
            "---\n\n"
            f"# {name}\n\n"
            f"{body}\n"
        ),
        "system_prompt.md": (
            "You are the GM for this roleplay scenario.\n"
            "Maintain consistency with the scenario, characters, lore, memory, and current state.\n"
            "Respond in Japanese unless the user explicitly asks otherwise.\n"
        ),
        "state/current.json": '{\n  "characters": {},\n  "flags": {}\n}\n',
        "startings/default.md": (
            "---\n"
            "type: starting\n"
            "id: default\n"
            "name: 通常開始\n"
            "---\n\n"
            "物語はここから始まります。\n"
        ),
    }


def _persona_summaries(vault: Vault) -> list[dict[str, str]]:
    return [{"id": persona_id, "name": load_persona(vault, persona_id).name} for persona_id in list_personas(vault)]


def _persona_detail(vault: Vault, persona_id: str) -> dict[str, Any]:
    persona = load_persona(vault, persona_id)
    content = vault.read_text(f"rp/personas/{persona_id}.md")
    return {"id": persona.id, "name": persona.name, "body": persona.body, "metadata": persona.metadata, "content": content}


def _update_persona(vault: Vault, persona_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    content = _require_string_payload(payload, "content")
    try:
        doc = parse_markdown(content)
    except FrontmatterError as exc:
        raise ApiBadRequest(f"Invalid persona frontmatter: {exc}") from exc
    metadata = doc.frontmatter
    if metadata.get("type") != "persona":
        raise ApiBadRequest("Persona content must have type: persona in frontmatter")
    if str(metadata.get("id", "")) != persona_id:
        raise ApiBadRequest(f"Persona id in frontmatter must match URL: {persona_id}")
    path = vault.resolve(f"rp/personas/{persona_id}.md")
    _atomic_write(path, content)
    return {"id": persona_id, "saved": True}


def _create_persona(vault: Vault, payload: dict[str, Any]) -> dict[str, Any]:
    persona_id = _validate_id(_require_string_payload(payload, "persona_id"), "persona")
    name = _require_string_payload(payload, "name")
    path = vault.resolve(f"rp/personas/{persona_id}.md")
    if path.exists():
        raise ApiBadRequest(f"Persona already exists: {persona_id}")
    content = f"---\ntype: persona\nid: {persona_id}\nname: {name}\n---\n\n# {name}\n\nペルソナの説明をここに記述します。\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, content)
    return {"id": persona_id, "name": name, "created": True}


def _profile_detail(vault: Vault, profile_id: str) -> dict[str, Any]:
    profile = load_profile(vault, profile_id)
    safe_data = {
        k: v for k, v in profile.data.items()
        if k not in HIDDEN_PROFILE_RESPONSE_FIELDS and k.lower() not in SECRET_PROFILE_FIELDS
    }
    return {"id": profile.id, "kind": profile.kind, "data": safe_data}


def _update_profile(vault: Vault, profile_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    extra = set(payload.keys()) - PROFILE_EDITABLE_FIELDS
    if extra:
        raise ApiBadRequest(
            f"Profile update only allows: {', '.join(sorted(PROFILE_EDITABLE_FIELDS))}. Got unexpected: {', '.join(sorted(extra))}"
        )
    lower_keys = {k.lower() for k in payload.keys()}
    suspicious = sorted(lower_keys & SECRET_PROFILE_FIELDS)
    if suspicious:
        raise ApiBadRequest(f"Profile must not contain secret fields: {', '.join(suspicious)}")
    if "model" in payload and not isinstance(payload["model"], str):
        raise ApiBadRequest("model must be a string")
    for num_field in ("temperature", "top_p", "top_k", "context_size", "max_tokens", "frequency_penalty", "presence_penalty", "repetition_penalty"):
        if num_field in payload and not isinstance(payload[num_field], (int, float)):
            raise ApiBadRequest(f"{num_field} must be a number")
    if "reasoning_effort" in payload and not isinstance(payload["reasoning_effort"], str):
        raise ApiBadRequest("reasoning_effort must be a string")
    raw = vault.load_json(f"rp/profiles/{profile_id}.json")
    if not isinstance(raw, dict):
        raise LoaderError(f"Profile is not a JSON object: {profile_id}")
    data = dict(raw)
    for field in PROFILE_EDITABLE_FIELDS:
        if field in payload:
            data[field] = payload[field]
    path = vault.resolve(f"rp/profiles/{profile_id}.json")
    _atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2))
    return {"id": profile_id, "saved": True}


def _atomic_write(path: Path, content: str) -> None:
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _profile_summaries(vault: Vault) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for profile_id in list_profiles(vault):
        profile = load_profile(vault, profile_id)
        data = profile.data
        summaries.append(
            {
                "id": profile.id,
                "kind": profile.kind,
                "model": data.get("model"),
                "context_size": data.get("context_size"),
                "temperature": data.get("temperature"),
                "top_p": data.get("top_p"),
                "max_tokens": data.get("max_tokens"),
            }
        )
    return summaries


def _session_summaries(vault: Vault, scenario_id: str) -> list[dict[str, Any]]:
    return [
        {
            "session_id": metadata.get("session_id"),
            "display_name": metadata.get("display_name", metadata.get("session_id")),
            "updated_at": metadata.get("updated_at"),
            "turn_count": metadata.get("turn_count", 0),
            "parent_session_id": metadata.get("parent_session_id"),
            "branched_from_turn": metadata.get("branched_from_turn"),
        }
        for metadata in list_session_metadata(vault, scenario_id)
    ]


def _session_detail_response(vault: Vault, scenario_id: str, session_id: str) -> dict[str, Any]:
    metadata = read_session_metadata(vault, scenario_id, session_id)
    active_turn = find_active_turn_job(vault, scenario_id, session_id)
    active_postprocess = find_active_postprocess_job(vault, scenario_id, session_id)
    return {
        "scenario_id": scenario_id,
        "session_id": session_id,
        "metadata": metadata,
        "pending_turn": _public_turn_job(active_turn) if active_turn is not None else None,
        "pending_postprocess": _public_postprocess_job(active_postprocess) if active_postprocess is not None else None,
    }


def _scenario_source_files(vault: Vault, scenario_id: str) -> list[dict[str, Any]]:
    load_scenario(vault, scenario_id)
    scenario_root = vault.resolve(f"rp/scenarios/{scenario_id}")
    files: list[dict[str, Any]] = []
    for path in sorted(scenario_root.rglob("*.md")):
        relative = path.relative_to(scenario_root).as_posix()
        if not _is_allowed_scenario_source_path(relative):
            continue
        files.append({"path": relative, "size": path.stat().st_size})
    return files


def _scenario_source_file(vault: Vault, scenario_id: str, source_path: str) -> dict[str, Any]:
    load_scenario(vault, scenario_id)
    safe_path = _validate_scenario_source_path(source_path)
    content = vault.read_text(f"rp/scenarios/{scenario_id}/{safe_path}")
    return {"scenario_id": scenario_id, "path": safe_path, "content": content}


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


def _scenario_startings_response(vault: Vault, scenario_id: str) -> dict[str, Any]:
    load_scenario(vault, scenario_id)
    startings = []
    for starting_id in list_startings(vault, scenario_id):
        starting = load_starting(vault, scenario_id, starting_id)
        startings.append(
            {
                "id": starting.id,
                "name": starting.name,
                "metadata": starting.metadata,
                "content": starting.body,
            }
        )
    return {"scenario_id": scenario_id, "startings": startings}


_BUSTUP_EXTENSION_ORDER: tuple[str, ...] = (".png", ".webp", ".jpg", ".jpeg", ".gif")


def _resolve_bustup_asset(vault: Vault, scenario_id: str, image_dir: str) -> tuple[str, bool]:
    """Resolve the bustup image for image_dir, trying allowed extensions in order.

    Returns (extension_with_dot, exists). When no file exists, returns (".png", False)
    so the path/URL keep the historical .png shape for backward compatibility.
    """
    for extension in _BUSTUP_EXTENSION_ORDER:
        if image_asset_path(vault, scenario_id, image_dir, "bustup", extension).is_file():
            return extension, True
    return ".png", False


def _scenario_character_bustups_response(vault: Vault, scenario_id: str) -> dict[str, Any]:
    load_scenario(vault, scenario_id)
    characters_path = vault.resolve(f"rp/scenarios/{scenario_id}/assets/characters.json")
    if not characters_path.is_file():
        return {"scenario_id": scenario_id, "characters": []}

    payload = vault.load_json(f"rp/scenarios/{scenario_id}/assets/characters.json")
    if not isinstance(payload, dict):
        raise ApiBadRequest("assets/characters.json root must be an object")

    characters: list[dict[str, Any]] = []
    for character_id, config in _character_asset_entries(payload):
        if not isinstance(character_id, str) or not is_locus_id(character_id) or not isinstance(config, dict):
            continue
        image_dir = config.get("image_dir") or _image_dir_from_base_path(config.get("image_base_path")) or character_id
        if not isinstance(image_dir, str) or not is_locus_id(image_dir):
            continue

        name = config.get("name", character_id)
        short_name = config.get("short_name", config.get("shortName", name))
        aliases = _character_aliases(character_id, config, name, short_name)
        bustup_ext, bustup_exists = _resolve_bustup_asset(vault, scenario_id, image_dir)
        characters.append(
            {
                "id": character_id,
                "name": name if isinstance(name, str) else character_id,
                "short_name": short_name if isinstance(short_name, str) else character_id,
                "aliases": aliases,
                "image_dir": image_dir,
                "bustup_path": f"{image_dir}/bustup{bustup_ext}",
                "bustup_url": image_asset_url(scenario_id, image_dir, "bustup", bustup_ext),
                "bustup_exists": bustup_exists,
            }
        )
    return {"scenario_id": scenario_id, "characters": characters}


def _character_asset_entries(payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    raw_characters = payload.get("characters")
    if isinstance(raw_characters, list):
        entries: list[tuple[str, dict[str, Any]]] = []
        for item in raw_characters:
            if not isinstance(item, dict):
                continue
            character_id = item.get("id")
            if isinstance(character_id, str):
                entries.append((character_id, item))
        return sorted(entries, key=lambda entry: entry[0])

    entries = [(character_id, config) for character_id, config in payload.items() if isinstance(config, dict)]
    return sorted(entries, key=lambda entry: entry[0])


def _image_dir_from_base_path(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = PurePosixPath(value.strip())
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        return None
    if len(path.parts) >= 3 and path.parts[-3:-1] == ("assets", "images"):
        return path.parts[-1]
    if len(path.parts) >= 2 and path.parts[-2] == "images":
        return path.parts[-1]
    return path.name or None


def _character_aliases(character_id: str, config: dict[str, Any], name: Any, short_name: Any) -> list[str]:
    aliases = [character_id]
    for value in (name, short_name):
        if isinstance(value, str) and value.strip():
            aliases.append(value.strip())
    raw_aliases = config.get("aliases", [])
    if isinstance(raw_aliases, list):
        aliases.extend(value.strip() for value in raw_aliases if isinstance(value, str) and value.strip())

    unique: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        if alias not in seen:
            seen.add(alias)
            unique.append(alias)
    return unique


def _update_scenario_source_file(vault: Vault, scenario_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    load_scenario(vault, scenario_id)
    safe_path = _validate_scenario_source_path(payload.get("path"))
    content = payload.get("content")
    if not isinstance(content, str):
        raise ApiBadRequest("source content must be a string")
    _validate_scenario_source_content(safe_path, content)
    path = vault.resolve(f"rp/scenarios/{scenario_id}/{safe_path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return {"scenario_id": scenario_id, "path": safe_path, "content": content, "saved": True}


def _create_scenario_source_file(vault: Vault, scenario_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    load_scenario(vault, scenario_id)
    safe_path = _validate_new_scenario_source_path(payload.get("path"))
    content = payload.get("content")
    if not isinstance(content, str):
        raise ApiBadRequest("source content must be a string")
    _validate_scenario_source_content(safe_path, content)
    path = vault.resolve(f"rp/scenarios/{scenario_id}/{safe_path}")
    if path.exists():
        raise ApiBadRequest("source file already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return {"scenario_id": scenario_id, "path": safe_path, "content": content, "created": True}


def _validate_scenario_source_content(safe_path: str, content: str) -> None:
    parts = PurePosixPath(safe_path).parts
    if len(parts) != 2 or parts[0] != "lore":
        return
    try:
        document = parse_markdown(content)
    except FrontmatterError as exc:
        raise ApiBadRequest(f"Invalid lore frontmatter: {exc}") from exc
    keywords = document.frontmatter.get("keywords")
    if keywords is None:
        return
    if not isinstance(keywords, list):
        raise ApiBadRequest("lore keywords must be a list")
    for keyword in keywords:
        if not isinstance(keyword, str):
            raise ApiBadRequest("lore keywords must contain strings only")
        if not keyword.strip():
            raise ApiBadRequest("lore keywords must not contain empty strings")


def _delete_scenario_source_file(vault: Vault, scenario_id: str, query: dict[str, list[str]]) -> dict[str, Any]:
    load_scenario(vault, scenario_id)
    safe_path = _validate_deletable_scenario_source_path(_query_string(query, "path"))
    parts = safe_path.split("/")
    if parts[0] == "startings" and len(parts) == 2:
        starting_id = parts[1].removesuffix(".md")
        try:
            delete_start(vault, scenario_id, starting_id)
        except StartError as exc:
            raise ApiBadRequest(str(exc)) from exc
    else:
        path = vault.resolve(f"rp/scenarios/{scenario_id}/{safe_path}")
        if not path.is_file():
            raise ApiBadRequest("source file does not exist")
        path.unlink()
    return {"scenario_id": scenario_id, "path": safe_path, "deleted": True}


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


def _scenario_state_template(vault: Vault, scenario_id: str) -> dict[str, Any]:
    load_scenario(vault, scenario_id)
    html_path = vault.resolve(f"rp/scenarios/{scenario_id}/state/view.html")
    css_path = vault.resolve(f"rp/scenarios/{scenario_id}/state/view.css")
    has_html = html_path.is_file()
    has_css = css_path.is_file()
    if not has_html and not has_css:
        return {"scenario_id": scenario_id, "has_template": False, "html": None, "css": None, "warnings": []}

    html = html_path.read_text(encoding="utf-8") if has_html else ""
    css = css_path.read_text(encoding="utf-8") if has_css else ""
    warnings: list[str] = []
    css_errors = _state_template_css_errors(css)
    if css_errors:
        css = ""
        warnings.extend(css_errors)
    return {"scenario_id": scenario_id, "has_template": True, "html": html, "css": css, "warnings": warnings}


def _state_template_css_errors(css: str) -> list[str]:
    if not css:
        return []
    checks = [
        (r"@import\b", "State template CSS must not use @import"),
        (r"\burl\s*\(", "State template CSS must not use url()"),
        (r"position\s*:\s*fixed\b", "State template CSS must not use position: fixed"),
        (r"position\s*:\s*absolute\b", "State template CSS must not use position: absolute"),
    ]
    return [message for pattern, message in checks if re.search(pattern, css, flags=re.IGNORECASE)]


def _scenario_rag_status(vault: Vault, scenario_id: str) -> dict[str, Any]:
    load_scenario(vault, scenario_id)
    memory_counts = _memory_file_counts(vault, scenario_id)
    index = read_rag_index(vault, scenario_id)
    rebuild_needed = rag_index_rebuild_needed(vault, scenario_id, index)
    stale_path = vault.resolve("rp/_cache/rag/stale.json")
    stale_payload: dict[str, Any] | None = None
    stale_error = ""
    if stale_path.is_file():
        try:
            loaded = vault.load_json("rp/_cache/rag/stale.json")
            if isinstance(loaded, dict):
                stale_payload = loaded
            else:
                stale_error = "stale marker root is not an object"
        except VaultError as exc:
            stale_error = str(exc)

    marker_scenario_id = stale_payload.get("scenario_id") if stale_payload else None
    stale_for_scenario = marker_scenario_id == scenario_id
    return {
        "scenario_id": scenario_id,
        "rag_index": {
            "implemented": True,
            "indexed": index is not None,
            "version": index.get("version") if index else None,
            "document_count": index.get("document_count") if index else 0,
            "indexed_at": index.get("indexed_at") if index else "",
            "rebuild_needed": rebuild_needed,
            "stale": stale_for_scenario or bool(stale_error) or rebuild_needed,
            "stale_marker_exists": stale_path.is_file(),
            "stale_marker_scenario_id": marker_scenario_id,
            "reason": stale_payload.get("reason") if stale_payload else "",
            "marked_at": stale_payload.get("marked_at") if stale_payload else "",
            "created_files": stale_payload.get("created_files", []) if stale_for_scenario else [],
            "error": stale_error,
        },
        "memory": {
            "counts": memory_counts,
            "total": sum(memory_counts.values()),
        },
    }


def _scenario_rag_rebuild_response(vault: Vault, scenario_id: str) -> dict[str, Any]:
    load_scenario(vault, scenario_id)
    index = rebuild_rag_index(vault, scenario_id)
    return {
        "scenario_id": scenario_id,
        "rebuilt": True,
        "index": {
            "version": index["version"],
            "document_count": index["document_count"],
            "indexed_at": index["indexed_at"],
            "incremental": index.get("incremental", {}),
        },
    }


def _scenario_memory_response(vault: Vault, scenario_id: str, *, session_id: str | None = None) -> dict[str, Any]:
    load_scenario(vault, scenario_id)
    base = vault.resolve(f"rp/scenarios/{scenario_id}")
    memory_root = base / "memory"
    kinds = ("session_summaries", "extracted_facts", "unresolved_threads")
    groups: dict[str, list[dict[str, Any]]] = {kind: [] for kind in kinds}
    index = read_rag_index(vault, scenario_id)
    indexed_paths = _rag_index_source_paths(index)
    stale_created_paths = set(_scenario_rag_status(vault, scenario_id)["rag_index"].get("created_files", []))

    for kind in kinds:
        directory = memory_root / kind
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            if not path.is_file():
                continue
            scenario_relative = path.relative_to(base).as_posix()
            try:
                document = vault.load_markdown(f"rp/scenarios/{scenario_id}/{scenario_relative}")
            except VaultFileError as exc:
                raise ApiBadRequest(f"memory markdown is unreadable: {scenario_relative}") from exc
            metadata = dict(document.frontmatter)
            if session_id is not None and metadata.get("session_id") != session_id:
                continue
            body = document.body.strip()
            stat = path.stat()
            normalized_metadata = _normalize_memory_metadata(metadata)
            groups[kind].append(
                {
                    "path": scenario_relative,
                    "kind": kind,
                    "memory_kind": normalized_metadata.get("memory_kind") or _memory_kind_from_folder(kind),
                    "title": _memory_title(path, normalized_metadata),
                    "metadata": normalized_metadata,
                    "content": body,
                    "excerpt": _timeline_excerpt(body, limit=120),
                    "updated_at": stat.st_mtime,
                    "rag_enabled": normalized_metadata.get("rag") is not False,
                    "in_index": scenario_relative in indexed_paths,
                    "stale_created": scenario_relative in stale_created_paths,
                    "status": normalized_metadata["status"],
                    "source": normalized_metadata["source"],
                    "confidence": normalized_metadata["confidence"],
                    "last_seen_turn": normalized_metadata.get("last_seen_turn"),
                    "characters": normalized_metadata.get("characters", []),
                    "locations": normalized_metadata.get("locations", []),
                    "topics": normalized_metadata.get("topics", []),
                }
            )

    for items in groups.values():
        items.sort(key=lambda item: (-item["updated_at"], item["path"]))

    return {
        "scenario_id": scenario_id,
        **({"session_id": session_id} if session_id is not None else {}),
        "groups": groups,
        "counts": {kind: len(items) for kind, items in groups.items()},
        "total": sum(len(items) for items in groups.values()),
    }


def _normalize_memory_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(metadata)
    status = normalized.get("status")
    if not isinstance(status, str) or not status.strip():
        normalized["status"] = "active"
    source = normalized.get("source")
    if not isinstance(source, str) or not source.strip():
        normalized["source"] = "unknown"
    confidence = normalized.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
        normalized["confidence"] = None
    for field in ("supersedes", "superseded_by", "characters", "locations", "topics"):
        value = normalized.get(field)
        if not isinstance(value, list):
            normalized[field] = []
        else:
            normalized[field] = [item for item in value if isinstance(item, str)]
    return normalized


def _markdown_with_frontmatter(frontmatter: dict[str, Any], body: str) -> str:
    return "---\n" + "\n".join(_yaml_lines(frontmatter)) + "\n---\n\n" + body.strip() + "\n"


def _yaml_lines(data: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for key, value in data.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {_yaml_scalar(item)}")
        else:
            lines.append(f"{key}: {_yaml_scalar(value)}")
    return lines


def _yaml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return str(value)
    text = str(value)
    if not text:
        return '""'
    if re.fullmatch(r"[A-Za-z0-9_./:+-]+", text):
        return text
    return json.dumps(text, ensure_ascii=False)


def _atomic_write_text(path: Path, content: str) -> None:
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _utc_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _rag_index_source_paths(index: dict[str, Any] | None) -> set[str]:
    documents = index.get("documents") if isinstance(index, dict) else []
    if not isinstance(documents, list):
        return set()
    return {item["source_path"] for item in documents if isinstance(item, dict) and isinstance(item.get("source_path"), str)}


def _memory_kind_from_folder(folder: str) -> str:
    return {
        "session_summaries": "session_summary",
        "extracted_facts": "fact",
        "unresolved_threads": "unresolved_thread",
    }.get(folder, "memory")


def _scenario_rag_vector_status(vault: Vault, scenario_id: str) -> dict[str, Any]:
    load_scenario(vault, scenario_id)
    config = get_embedding_config()
    index = read_vector_index(vault, scenario_id)
    rebuild_needed = vector_index_rebuild_needed(vault, scenario_id, config, index) if config.enabled else False
    return {
        "scenario_id": scenario_id,
        "embedding": config.as_safe_dict(),
        "vector_index": {
            "indexed": index is not None,
            "version": index.get("version") if index else None,
            "model": index.get("model") if index else None,
            "document_count": index.get("document_count") if index else 0,
            "indexed_at": index.get("indexed_at") if index else "",
            "rebuild_needed": rebuild_needed,
        },
    }


def _scenario_rag_rebuild_vectors_response(vault: Vault, scenario_id: str) -> dict[str, Any]:
    load_scenario(vault, scenario_id)
    config = get_embedding_config()
    if not config.enabled:
        raise ApiBadRequest("Embedding is not configured (set LOCUS_EMBEDDING_MODEL and endpoint env vars)")
    try:
        index = build_vector_index(vault, scenario_id, config)
    except EmbeddingError as exc:
        raise ApiBadRequest(str(exc)) from exc
    return {
        "scenario_id": scenario_id,
        "rebuilt": True,
        "index": {
            "version": index["version"],
            "model": index["model"],
            "document_count": index["document_count"],
            "indexed_at": index["indexed_at"],
        },
    }


def _memory_title(path: Path, metadata: dict[str, Any]) -> str:
    for key in ("title", "name", "id"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return path.stem


def _memory_file_counts(vault: Vault, scenario_id: str) -> dict[str, int]:
    base = vault.resolve(f"rp/scenarios/{scenario_id}/memory")
    counts = {"session_summaries": 0, "extracted_facts": 0, "unresolved_threads": 0}
    if not base.exists():
        return counts
    for folder in counts:
        directory = base / folder
        if directory.is_dir():
            counts[folder] = len([path for path in directory.glob("*.md") if path.is_file()])
    return counts


def _create_session_response(vault: Vault, payload: dict[str, Any]) -> ApiResponse:
    scenario_id = _require_id(payload, "scenario_id")
    persona_id = _require_id(payload, "persona_id")
    rp_profile_id = _require_id(payload, "rp_profile_id")
    summary_profile_id = _optional_id(payload, "summary_profile_id")
    starting_id = _optional_id(payload, "starting_id")
    session_id = _optional_id(payload, "session_id") or next_session_id(vault, scenario_id)
    display_name = payload.get("display_name")
    if display_name is not None and not isinstance(display_name, str):
        raise ApiBadRequest("display_name must be a string")

    load_scenario(vault, scenario_id)
    load_persona(vault, persona_id)
    load_profile(vault, rp_profile_id)
    if summary_profile_id is not None:
        load_profile(vault, summary_profile_id)
    starting = load_starting(vault, scenario_id, starting_id) if starting_id is not None else None

    initial_state_vault_path: str | None = None
    if starting_id is not None:
        try:
            manifest = read_start_manifest(vault, scenario_id, starting_id)
        except StartError as exc:
            raise ApiBadRequest(str(exc)) from exc
        settings = read_scenario_settings(vault, scenario_id)
        if settings.get("prompt_graph_mode") == "per_start":
            initial_state_vault_path = resolve_initial_state_path(scenario_id, starting_id, manifest)

    metadata = create_session(
        vault,
        SessionMetadata(
            session_id=session_id,
            scenario_id=scenario_id,
            persona_id=persona_id,
            rp_profile_id=rp_profile_id,
            summary_profile_id=summary_profile_id,
            starting_id=starting_id,
        ),
        initial_state_vault_path=initial_state_vault_path,
    )
    if starting is not None:
        append_session_log(
            vault,
            scenario_id,
            session_id,
            turn=0,
            role="assistant",
            content=starting.body,
            extra={"starting_id": starting.id, "starting_name": starting.name, "is_starting": True},
        )
    if display_name:
        metadata["display_name"] = display_name
    if starting_id is not None or starting is not None or display_name:
        write_session_metadata(vault, scenario_id, session_id, metadata)
    return _json_response({"session": metadata}, status=201)


def _create_branch_session_response(
    vault: Vault,
    scenario_id: str,
    parent_session_id: str,
    payload: dict[str, Any],
) -> ApiResponse:
    branched_from_turn = payload.get("branched_from_turn")
    if not isinstance(branched_from_turn, int) or branched_from_turn < 0:
        raise ApiBadRequest("branched_from_turn must be a non-negative integer")
    display_name = payload.get("display_name")
    if display_name is not None and not isinstance(display_name, str):
        raise ApiBadRequest("display_name must be a string")

    parent_metadata = read_session_metadata(vault, scenario_id, parent_session_id)
    persona_id = _require_metadata_id(parent_metadata, "persona_id")
    rp_profile_id = _require_metadata_id(parent_metadata, "rp_profile_id")
    summary_profile_id = _optional_metadata_id(parent_metadata, "summary_profile_id")
    child_session_id = _optional_id(payload, "session_id") or next_session_id(vault, scenario_id)

    copied_entries = [
        entry
        for entry in read_session_log(vault, scenario_id, parent_session_id)
        if isinstance(entry.get("turn"), int) and entry["turn"] <= branched_from_turn
    ]
    child_turn_count = max(
        [entry["turn"] for entry in copied_entries if isinstance(entry.get("turn"), int)],
        default=0,
    )
    state_snapshot_available = _session_state_snapshot_exists(vault, scenario_id, parent_session_id, branched_from_turn)

    metadata = create_session(
        vault,
        SessionMetadata(
            session_id=child_session_id,
            scenario_id=scenario_id,
            persona_id=persona_id,
            rp_profile_id=rp_profile_id,
            summary_profile_id=summary_profile_id,
            turn_count=child_turn_count,
        ),
    )
    metadata["display_name"] = display_name or f"{parent_metadata.get('display_name', parent_session_id)} branch {branched_from_turn}"
    metadata["parent_session_id"] = parent_session_id
    metadata["branched_from_turn"] = branched_from_turn
    if "active_mods" in parent_metadata:
        metadata["active_mods"] = parent_metadata["active_mods"]
    if "pinned_characters" in parent_metadata:
        metadata["pinned_characters"] = parent_metadata["pinned_characters"]
    for note_key in ("user_note", "session_note", "scene_note"):
        if note_key in parent_metadata:
            metadata[note_key] = parent_metadata[note_key]
    copy_session_state_for_turn(vault, scenario_id, parent_session_id, child_session_id, branched_from_turn)
    metadata["state_copied"] = True
    metadata["state_snapshot_available"] = state_snapshot_available
    metadata["state_snapshot_source"] = "snapshot" if state_snapshot_available else "current_state_fallback"
    metadata["state_snapshot_note"] = _branch_state_snapshot_note(state_snapshot_available)
    write_session_metadata(vault, scenario_id, child_session_id, metadata)

    for entry in copied_entries:
        role = entry.get("role")
        content = entry.get("content")
        turn = entry.get("turn")
        if not isinstance(role, str) or not isinstance(content, str) or not isinstance(turn, int):
            continue
        extra = {
            key: value
            for key, value in entry.items()
            if key not in {"turn", "role", "content", "timestamp"}
        }
        append_session_log(
            vault,
            scenario_id,
            child_session_id,
            turn=turn,
            role=role,
            content=content,
            timestamp=entry.get("timestamp") if isinstance(entry.get("timestamp"), str) else None,
            extra=extra,
        )

    return _json_response({"session": metadata, "copied_entries": len(copied_entries)}, status=201)


def _update_session_settings_response(
    vault: Vault,
    scenario_id: str,
    session_id: str,
    payload: dict[str, Any],
) -> ApiResponse:
    metadata = read_session_metadata(vault, scenario_id, session_id)
    user_note = payload.get("user_note")
    if user_note is not None and not isinstance(user_note, str):
        raise ApiBadRequest("user_note must be a string")
    session_note = payload.get("session_note")
    if session_note is not None and not isinstance(session_note, str):
        raise ApiBadRequest("session_note must be a string")
    scene_note = payload.get("scene_note")
    if scene_note is not None and not isinstance(scene_note, str):
        raise ApiBadRequest("scene_note must be a string")
    display_name = payload.get("display_name")
    if display_name is not None and not isinstance(display_name, str):
        raise ApiBadRequest("display_name must be a string")
    bookmarked_turns = payload.get("bookmarked_turns")
    if bookmarked_turns is not None:
        bookmarked_turns = _validate_bookmarked_turns(bookmarked_turns)
    rp_profile_id = _optional_id(payload, "rp_profile_id")
    if rp_profile_id is not None:
        load_profile(vault, rp_profile_id)
    summary_profile_id = _optional_id(payload, "summary_profile_id")
    if summary_profile_id is not None:
        load_profile(vault, summary_profile_id)

    updated = dict(metadata)
    if session_note is not None:
        updated["session_note"] = session_note
    elif user_note is not None:
        updated["session_note"] = user_note
    if scene_note is not None:
        updated["scene_note"] = scene_note
    if display_name is not None:
        updated["display_name"] = display_name
    if bookmarked_turns is not None:
        updated["bookmarked_turns"] = bookmarked_turns
    if rp_profile_id is not None:
        updated["rp_profile_id"] = rp_profile_id
    if summary_profile_id is not None:
        updated["summary_profile_id"] = summary_profile_id
    write_session_metadata(vault, scenario_id, session_id, updated)
    return _json_response({"session": updated})


def _session_pins_response(vault: Vault, scenario_id: str, session_id: str) -> dict[str, Any]:
    metadata = read_session_metadata(vault, scenario_id, session_id)
    active_mods: list[str] = _safe_list(metadata.get("active_mods"))
    pinned_characters: list[str] = _safe_list(metadata.get("pinned_characters"))
    available_mods = list_available_mods(vault, scenario_id)
    available_characters = list_available_characters(vault, scenario_id)
    warnings = _pin_warnings(vault, scenario_id, active_mods, pinned_characters)
    return {
        "scenario_id": scenario_id,
        "session_id": session_id,
        "active_mods": active_mods,
        "pinned_characters": pinned_characters,
        "available_mods": available_mods,
        "available_characters": available_characters,
        "warnings": warnings,
    }


def _update_session_pins_response(
    vault: Vault,
    scenario_id: str,
    session_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    active_mods_raw = payload.get("active_mods")
    pinned_chars_raw = payload.get("pinned_characters")
    if active_mods_raw is not None and not isinstance(active_mods_raw, list):
        raise ApiBadRequest("active_mods must be an array")
    if pinned_chars_raw is not None and not isinstance(pinned_chars_raw, list):
        raise ApiBadRequest("pinned_characters must be an array")

    active_mods = _validate_pin_paths(active_mods_raw, "lore") if active_mods_raw is not None else None
    pinned_characters = _validate_pin_paths(pinned_chars_raw, "characters") if pinned_chars_raw is not None else None

    metadata = read_session_metadata(vault, scenario_id, session_id)
    updated = dict(metadata)
    if active_mods is not None:
        updated["active_mods"] = active_mods
    if pinned_characters is not None:
        updated["pinned_characters"] = pinned_characters
    write_session_metadata(vault, scenario_id, session_id, updated)

    available_mods = list_available_mods(vault, scenario_id)
    available_characters = list_available_characters(vault, scenario_id)
    warnings = _pin_warnings(
        vault,
        scenario_id,
        updated.get("active_mods", []),
        updated.get("pinned_characters", []),
    )
    return {
        "scenario_id": scenario_id,
        "session_id": session_id,
        "active_mods": updated.get("active_mods", []),
        "pinned_characters": updated.get("pinned_characters", []),
        "available_mods": available_mods,
        "available_characters": available_characters,
        "warnings": warnings,
    }


def _update_session_starting_response(
    vault: Vault,
    scenario_id: str,
    session_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    starting_id = _optional_id(payload, "starting_id")
    read_session_metadata(vault, scenario_id, session_id)
    delete_session_log_entry(vault, scenario_id, session_id, 0, "assistant")
    metadata = read_session_metadata(vault, scenario_id, session_id)
    if starting_id is not None:
        starting = load_starting(vault, scenario_id, starting_id)
        append_session_log(
            vault, scenario_id, session_id,
            turn=0, role="assistant", content=starting.body,
            extra={"starting_id": starting.id, "starting_name": starting.name, "is_starting": True},
        )
        metadata["starting_id"] = starting_id
    else:
        metadata.pop("starting_id", None)
    write_session_metadata(vault, scenario_id, session_id, metadata)
    return _session_log_response(vault, scenario_id, session_id)

def _validate_pin_paths(paths: list[Any], expected_folder: str) -> list[str]:
    validated: list[str] = []
    for item in paths:
        if not isinstance(item, str):
            raise ApiBadRequest(f"Pin path must be a string, got: {type(item).__name__}")
        parts = item.split("/")
        if (
            "\\" in item
            or any(p in ("", ".", "..") for p in parts)
            or len(parts) != 2
            or parts[0] != expected_folder
            or not parts[1].endswith(".md")
        ):
            raise ApiBadRequest(f"Invalid pin path: {item}")
        validated.append(item)
    return validated


def _pin_warnings(
    vault: Vault,
    scenario_id: str,
    active_mods: list[str],
    pinned_characters: list[str],
) -> list[str]:
    warnings: list[str] = []
    for path in active_mods:
        doc = load_scenario_file(vault, scenario_id, path)
        if doc is None:
            warnings.append(f"{path}: file not found")
        elif doc.metadata.get("mod") is not True:
            warnings.append(f"{path}: mod: true not set")
    for path in pinned_characters:
        doc = load_scenario_file(vault, scenario_id, path)
        if doc is None:
            warnings.append(f"{path}: file not found")
    return warnings


def _safe_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


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
        result = finalize_gm_turn_fast(
            vault,
            scenario_id=scenario_id,
            session_id=session_id,
            user_message=user_message,
            assistant_content=completion.content,
            prepared=prepared,
            response_duration_ms=response_duration_ms,
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
            result = finalize_gm_turn_fast(
                vault,
                scenario_id=scenario_id,
                session_id=session_id,
                user_message=user_message,
                assistant_content=assistant_content,
                prepared=prepared,
                response_duration_ms=response_duration_ms,
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


def _session_log_response(
    vault: Vault,
    scenario_id: str,
    session_id: str,
    query: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    metadata = read_session_metadata(vault, scenario_id, session_id)
    scenario = load_scenario(vault, scenario_id)
    all_entries = read_session_log(vault, scenario_id, session_id)
    page_info = _session_log_page_info(all_entries, query or {})
    entries = []
    for entry in page_info["entries"]:
        payload = dict(entry)
        role = payload.get("role")
        content = payload.get("content")
        if role == "assistant" and isinstance(content, str):
            payload["segments"] = [segment_payload(segment) for segment in parse_image_markers(content, scenario=scenario, vault=vault)]
        entries.append(payload)
    return {
        "scenario_id": scenario_id,
        "session_id": session_id,
        "metadata": metadata,
        "log": entries,
        "pagination": {
            "mode": page_info["mode"],
            "turn_limit": page_info["turn_limit"],
            "before_turn": page_info["before_turn"],
            "min_turn": page_info["min_turn"],
            "max_turn": page_info["max_turn"],
            "total_turns": page_info["total_turns"],
            "has_more_before": page_info["has_more_before"],
        },
    }


def _session_log_page_info(entries: list[dict[str, Any]], query: dict[str, list[str]]) -> dict[str, Any]:
    turn_limit = _optional_positive_int_query(query, "turn_limit")
    before_turn = _optional_non_negative_int_query(query, "before_turn")
    from_turn = _optional_non_negative_int_query(query, "from_turn")
    turn_values = sorted({entry["turn"] for entry in entries if isinstance(entry.get("turn"), int)})
    if turn_limit is None:
        return {
            "mode": "all",
            "turn_limit": None,
            "before_turn": before_turn,
            "from_turn": from_turn,
            "entries": entries,
            "min_turn": turn_values[0] if turn_values else None,
            "max_turn": turn_values[-1] if turn_values else None,
            "total_turns": len(turn_values),
            "has_more_before": False,
            "has_more_after": False,
        }

    if from_turn is not None:
        eligible_turns = [turn for turn in turn_values if turn >= from_turn]
        selected_turns = set(eligible_turns[:turn_limit])
    else:
        eligible_turns = [turn for turn in turn_values if before_turn is None or turn < before_turn]
        selected_turns = set(eligible_turns[-turn_limit:])

    selected_entries = [
        entry
        for entry in entries
        if isinstance(entry.get("turn"), int) and entry["turn"] in selected_turns
    ]
    selected_values = sorted(selected_turns)
    first_selected = selected_values[0] if selected_values else None
    last_selected = selected_values[-1] if selected_values else None
    return {
        "mode": "turn_page",
        "turn_limit": turn_limit,
        "before_turn": before_turn,
        "from_turn": from_turn,
        "entries": selected_entries,
        "min_turn": first_selected,
        "max_turn": last_selected,
        "total_turns": len(turn_values),
        "has_more_before": first_selected is not None and any(turn < first_selected for turn in turn_values),
        "has_more_after": last_selected is not None and any(turn > last_selected for turn in turn_values),
    }


def _session_latest_prompt_response(vault: Vault, scenario_id: str, session_id: str) -> dict[str, Any]:
    read_session_metadata(vault, scenario_id, session_id)
    latest = read_latest_session_prompt(vault, scenario_id, session_id)
    if latest is None:
        return {
            "scenario_id": scenario_id,
            "session_id": session_id,
            "has_prompt": False,
            "message": "まだ送信済みプロンプトはありません。次の会話後にここへ表示されます。",
            "prompt": None,
        }
    return {
        "scenario_id": scenario_id,
        "session_id": session_id,
        "has_prompt": True,
        "message": "",
        "prompt": latest,
    }


def _session_timeline_response(vault: Vault, scenario_id: str, session_id: str) -> dict[str, Any]:
    metadata = read_session_metadata(vault, scenario_id, session_id)
    entries = read_session_log(vault, scenario_id, session_id)
    branch_map = _session_branches_by_turn(vault, scenario_id, session_id)
    bookmarks = _metadata_bookmarked_turns(metadata)
    timeline: list[dict[str, Any]] = []
    for index, entry in enumerate(entries, start=1):
        role = entry.get("role")
        if role not in {"user", "assistant"}:
            continue
        turn = entry.get("turn")
        if not isinstance(turn, int):
            turn = index
        content = entry.get("content")
        if not isinstance(content, str):
            content = ""
        timeline.append(
            {
                "turn": turn,
                "role": role,
                "excerpt": _timeline_excerpt(content),
                "timestamp": entry.get("timestamp"),
                "bookmarked": turn in bookmarks,
                "branches": branch_map.get(turn, []),
                "state_snapshot_available": _session_state_snapshot_exists(vault, scenario_id, session_id, turn),
            }
        )
    return {"scenario_id": scenario_id, "session_id": session_id, "metadata": metadata, "timeline": timeline}


def _session_branches_by_turn(vault: Vault, scenario_id: str, session_id: str) -> dict[int, list[dict[str, Any]]]:
    branches: dict[int, list[dict[str, Any]]] = {}
    for metadata in list_session_metadata(vault, scenario_id):
        if metadata.get("parent_session_id") != session_id:
            continue
        turn = metadata.get("branched_from_turn")
        if not isinstance(turn, int):
            continue
        branches.setdefault(turn, []).append(
            {
                "session_id": metadata.get("session_id"),
                "display_name": metadata.get("display_name", metadata.get("session_id")),
                "turn_count": metadata.get("turn_count", 0),
                "updated_at": metadata.get("updated_at"),
                "state_snapshot_available": metadata.get("state_snapshot_available"),
                "state_snapshot_source": metadata.get("state_snapshot_source"),
                "state_snapshot_note": metadata.get("state_snapshot_note"),
            }
        )
    return branches


def _session_state_snapshot_exists(vault: Vault, scenario_id: str, session_id: str, turn: int) -> bool:
    try:
        read_session_state_snapshot(vault, scenario_id, session_id, turn)
    except VaultError:
        return False
    return True


def _branch_state_snapshot_note(snapshot_available: bool) -> str:
    if snapshot_available:
        return "Branch state was copied from the parent session snapshot for branched_from_turn."
    return (
        "Parent state snapshot for branched_from_turn was missing. "
        "Branch state was copied from the parent session current state fallback."
    )


def _metadata_bookmarked_turns(metadata: dict[str, Any]) -> set[int]:
    raw = metadata.get("bookmarked_turns", [])
    if not isinstance(raw, list):
        return set()
    return {turn for turn in raw if isinstance(turn, int)}


def _validate_bookmarked_turns(value: Any) -> list[int]:
    if not isinstance(value, list):
        raise ApiBadRequest("bookmarked_turns must be a list")
    turns: set[int] = set()
    for item in value:
        if not isinstance(item, int) or item < 0:
            raise ApiBadRequest("bookmarked_turns must contain non-negative integers")
        turns.add(item)
    return sorted(turns)


def _timeline_excerpt(content: str, limit: int = 80) -> str:
    compact = " ".join(content.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _image_response(vault: Vault, scenario_id: str, character_id: str, filename: str) -> ApiResponse:
    scenario_id = _validate_id(scenario_id, "scenario")
    dot_pos = filename.rfind(".")
    if dot_pos < 0:
        raise ImageMarkerError(f"Invalid image filename: {filename}")
    extension = filename[dot_pos:]
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ImageMarkerError(f"Invalid image filename: {filename}")
    situation_id = filename[:dot_pos]
    path = image_asset_path(vault, scenario_id, character_id, situation_id, extension)
    if not path.is_file():
        return _json_response({"error": "not_found", "message": "Image asset not found"}, status=404)
    return ApiResponse(
        status=200,
        content_type=ALLOWED_IMAGE_EXTENSIONS[extension],
        body=path.read_bytes(),
        last_modified=path.stat().st_mtime,
    )


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


def _json_response(payload: dict[str, Any], status: int = 200) -> ApiResponse:
    return ApiResponse(
        status=status,
        content_type="application/json; charset=utf-8",
        body=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
    )


def _sse_event(event: str, payload: dict[str, Any]) -> bytes:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {data}\n\n".encode("utf-8")


def _duration_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))


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
        return {"state_updated": True, "state_path": path, "state_update_error": None}
    except Exception as exc:
        return {"state_updated": False, "state_update_error": f"{type(exc).__name__}: {exc}"}


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


# ---------------------------------------------------------------------------
# ZIP export / import
# ---------------------------------------------------------------------------

def _scenario_export_response(vault: Vault, scenario_id: str) -> ApiResponse:
    from app.scenario_zip import export_scenario_zip
    from app.vault import VaultPathError
    try:
        zip_bytes = export_scenario_zip(vault, scenario_id)
    except VaultPathError as exc:
        return _json_response({"error": "not_found", "message": str(exc)}, status=404)
    return ApiResponse(
        status=200,
        content_type="application/zip",
        body=zip_bytes,
        headers=(("Content-Disposition", f'attachment; filename="{scenario_id}.zip"'),),
    )


def _scenario_import_response(
    vault: Vault,
    zip_bytes: bytes,
    query: dict[str, list[str]],
) -> ApiResponse:
    from app.scenario_zip import ScenarioAlreadyExistsError, ScenarioZipError, import_scenario_zip
    scenario_id = query.get("scenario_id", [""])[0].strip()
    if not scenario_id:
        raise ApiBadRequest("scenario_id query parameter is required")
    try:
        result = import_scenario_zip(vault, zip_bytes, scenario_id)
    except ScenarioAlreadyExistsError as exc:
        return _json_response({"error": "ScenarioAlreadyExistsError", "message": str(exc)}, status=409)
    except ScenarioZipError as exc:
        return _json_response({"error": "ScenarioZipError", "message": str(exc)}, status=400)
    return _json_response(result, status=201)

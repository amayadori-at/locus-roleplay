from __future__ import annotations

from typing import Any
from app.api_validation import (
    ApiBadRequest,
    optional_id as _optional_id,
    optional_metadata_id as _optional_metadata_id,
    optional_non_negative_int_query as _optional_non_negative_int_query,
    optional_positive_int_query as _optional_positive_int_query,
    require_id as _require_id,
    require_metadata_id as _require_metadata_id,
)
from app.images import parse_image_markers
from app.loaders import load_persona, load_profile, load_scenario, load_starting
from app.postprocess_jobs import find_active_postprocess_job
from app.scenario_settings import read_scenario_settings
from app.starts import StartError, read_start_manifest, resolve_initial_state_path
from app.rag import list_available_characters, list_available_mods, load_scenario_file
from app.state_session import (
    SessionMetadata,
    append_session_log,
    copy_session_state_for_turn,
    create_session,
    list_session_metadata,
    next_session_id,
    read_latest_session_prompt,
    read_session_log,
    read_session_metadata,
    read_session_state_snapshot,
    write_session_metadata,
    delete_session_log_entry,
)
from app.turn_payloads import segment_payload
from app.turn_jobs import find_active_turn_job
from app.vault import Vault, VaultError
from app.api.common import ApiResponse, _json_response, _timeline_excerpt
from app.api.turns import _public_postprocess_job, _public_turn_job


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

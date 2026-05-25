from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from app.loaders import ModelProfile
from app.memory_summarizer import run_memory_summary, should_update_memory
from app.reasoning import sanitize_log_entries
from app.state_updater import run_state_update
from app.state_session import read_session_metadata, write_session_metadata
from app.vault import Vault


class ChatCompletionClient(Protocol):
    def create_chat_completion(
        self, profile: ModelProfile | dict[str, Any], messages: list[dict[str, str]]
    ) -> Any:
        ...


def run_turn_postprocess(
    vault: Vault,
    *,
    scenario_id: str,
    session_id: str,
    turn: int,
    metadata: dict[str, Any],
    scenario_metadata: dict[str, Any],
    recent_log: list[dict[str, Any]],
    user_message: str,
    assistant_content: str,
    state_model_client: ChatCompletionClient | None,
) -> dict[str, Any]:
    state_updated = False
    state_update_error: str | None = None
    sanitized_recent_log = sanitize_log_entries(recent_log)
    summary_profile_id = metadata.get("summary_profile_id")
    if state_model_client is not None and isinstance(summary_profile_id, str) and summary_profile_id.strip():
        try:
            run_state_update(
                vault,
                scenario_id=scenario_id,
                session_id=session_id,
                turn=turn,
                profile_id=summary_profile_id,
                user_message=user_message,
                gm_response=assistant_content,
                model_client=state_model_client,
                recent_context=sanitized_recent_log,
            )
            state_updated = True
        except Exception as exc:
            state_update_error = f"{type(exc).__name__}: {exc}"

    memory_updated = False
    memory_update_error: str | None = None
    memory_files: list[str] = []
    memory_profile_id = metadata.get("summary_profile_id")
    if (
        state_model_client is not None
        and isinstance(memory_profile_id, str)
        and memory_profile_id.strip()
        and should_update_memory(scenario_metadata, turn)
    ):
        try:
            memory_result = run_memory_summary(
                vault,
                scenario_id=scenario_id,
                session_id=session_id,
                turn=turn,
                profile_id=memory_profile_id,
                model_client=state_model_client,
            )
            memory_updated = bool(memory_result.created_files)
            memory_files = memory_result.created_files
        except Exception as exc:
            memory_update_error = f"{type(exc).__name__}: {exc}"

    metadata_patch = _postprocess_metadata_patch(
        turn=turn,
        state_attempted=state_model_client is not None and isinstance(summary_profile_id, str) and summary_profile_id.strip(),
        state_update_error=state_update_error,
        memory_attempted=(
            state_model_client is not None
            and isinstance(memory_profile_id, str)
            and memory_profile_id.strip()
            and should_update_memory(scenario_metadata, turn)
        ),
        memory_update_error=memory_update_error,
    )
    if metadata_patch:
        current_metadata = read_session_metadata(vault, scenario_id, session_id)
        updated_metadata = dict(current_metadata)
        for key, value in metadata_patch.items():
            if value is None:
                updated_metadata.pop(key, None)
            else:
                updated_metadata[key] = value
        write_session_metadata(vault, scenario_id, session_id, updated_metadata)

    return {
        "state_updated": state_updated,
        "state_update_error": state_update_error,
        "memory_updated": memory_updated,
        "memory_update_error": memory_update_error,
        "memory_files": memory_files,
        "metadata_patch": metadata_patch,
    }


def _postprocess_metadata_patch(
    *,
    turn: int,
    state_attempted: bool,
    state_update_error: str | None,
    memory_attempted: bool,
    memory_update_error: str | None,
) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    if state_update_error:
        patch["last_state_error"] = _error_metadata(turn, state_update_error)
    elif state_attempted:
        patch["last_state_error"] = None

    if memory_update_error:
        patch["last_memory_error"] = _error_metadata(turn, memory_update_error)
    elif memory_attempted:
        patch["last_memory_error"] = None
    return patch


def _error_metadata(turn: int, error: str) -> dict[str, Any]:
    return {
        "turn": turn,
        "error": error,
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }

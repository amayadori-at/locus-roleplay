from __future__ import annotations

from typing import Any, Protocol

from app.loaders import ModelProfile
from app.memory_summarizer import run_memory_summary, should_update_memory
from app.state_updater import run_state_update
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
                recent_context=recent_log,
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

    return {
        "state_updated": state_updated,
        "state_update_error": state_update_error,
        "memory_updated": memory_updated,
        "memory_update_error": memory_update_error,
        "memory_files": memory_files,
    }

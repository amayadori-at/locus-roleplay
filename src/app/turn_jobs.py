from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.ids import is_locus_id
from app.state_session import read_session_metadata
from app.turn_payloads import turn_result_payload
from app.turn_loop import ChatCompletionClient, TurnResult, run_gm_turn
from app.vault import Vault, VaultError


class TurnJobError(VaultError):
    """Raised when turn job persistence or execution cannot proceed."""


ACTIVE_TURN_JOB_STATUSES = frozenset({"queued", "running"})


def next_turn_job_id(vault: Vault, scenario_id: str, session_id: str) -> tuple[str, int]:
    metadata = read_session_metadata(vault, scenario_id, session_id)
    current = metadata.get("turn_count", 0)
    if not isinstance(current, int) or current < 0:
        raise TurnJobError("Session metadata turn_count must be a non-negative integer")
    turn = current + 1
    return f"turn_{turn:04d}", turn


def read_turn_job(vault: Vault, scenario_id: str, session_id: str, turn_id: str) -> dict[str, Any]:
    _validate_ids(scenario_id, session_id, turn_id)
    path = _turn_job_path(vault, scenario_id, session_id, turn_id)
    if not path.is_file():
        raise TurnJobError(f"Turn job not found: {turn_id}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TurnJobError(f"Invalid turn job JSON: {turn_id}") from exc
    if not isinstance(payload, dict):
        raise TurnJobError("Turn job must be a JSON object")
    return payload


def find_active_turn_job(vault: Vault, scenario_id: str, session_id: str) -> dict[str, Any] | None:
    _validate_ids(scenario_id, session_id)
    directory = _turn_jobs_dir(vault, scenario_id, session_id)
    if not directory.is_dir():
        return None
    for path in sorted(directory.glob("turn_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("status") in ACTIVE_TURN_JOB_STATUSES:
            return payload
    return None


def start_turn_job(
    vault: Vault,
    *,
    scenario_id: str,
    session_id: str,
    user_message: str,
    model_client: ChatCompletionClient,
    state_model_client: ChatCompletionClient | None,
) -> dict[str, Any]:
    if not isinstance(user_message, str) or not user_message.strip():
        raise TurnJobError("user_message must be a non-empty string")
    _validate_ids(scenario_id, session_id)
    active = find_active_turn_job(vault, scenario_id, session_id)
    if active is not None:
        raise TurnJobError("A turn job is already running for this session")

    turn_id, turn = next_turn_job_id(vault, scenario_id, session_id)
    now = _now_iso()
    payload: dict[str, Any] = {
        "turn_id": turn_id,
        "scenario_id": scenario_id,
        "session_id": session_id,
        "turn": turn,
        "status": "queued",
        "user_message": user_message,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
        "error": None,
        "result": None,
    }
    write_turn_job(vault, scenario_id, session_id, turn_id, payload)

    thread = threading.Thread(
        target=_run_turn_job,
        kwargs={
            "vault": vault,
            "scenario_id": scenario_id,
            "session_id": session_id,
            "turn_id": turn_id,
            "user_message": user_message,
            "model_client": model_client,
            "state_model_client": state_model_client,
        },
        daemon=True,
    )
    thread.start()
    return payload


def write_turn_job(
    vault: Vault,
    scenario_id: str,
    session_id: str,
    turn_id: str,
    payload: dict[str, Any],
) -> None:
    _validate_ids(scenario_id, session_id, turn_id)
    if not isinstance(payload, dict):
        raise TurnJobError("Turn job payload must be a JSON object")
    path = _turn_job_path(vault, scenario_id, session_id, turn_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        temp_path.write_text(raw, encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _run_turn_job(
    *,
    vault: Vault,
    scenario_id: str,
    session_id: str,
    turn_id: str,
    user_message: str,
    model_client: ChatCompletionClient,
    state_model_client: ChatCompletionClient | None,
) -> None:
    _update_turn_job(vault, scenario_id, session_id, turn_id, {"status": "running", "started_at": _now_iso()})
    try:
        result = run_gm_turn(
            vault,
            scenario_id=scenario_id,
            session_id=session_id,
            user_message=user_message,
            model_client=model_client,
            state_model_client=state_model_client,
        )
        _update_turn_job(
            vault,
            scenario_id,
            session_id,
            turn_id,
            {
                "status": "completed",
                "completed_at": _now_iso(),
                "result": turn_result_payload(result),
                "error": None,
            },
        )
    except Exception as exc:
        _update_turn_job(
            vault,
            scenario_id,
            session_id,
            turn_id,
            {
                "status": "failed",
                "completed_at": _now_iso(),
                "error": {"type": type(exc).__name__, "message": str(exc)},
            },
        )


def _update_turn_job(
    vault: Vault,
    scenario_id: str,
    session_id: str,
    turn_id: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    payload = read_turn_job(vault, scenario_id, session_id, turn_id)
    payload.update(updates)
    payload["updated_at"] = _now_iso()
    write_turn_job(vault, scenario_id, session_id, turn_id, payload)
    return payload


def _turn_jobs_dir(vault: Vault, scenario_id: str, session_id: str) -> Path:
    return vault.resolve(f"rp/scenarios/{scenario_id}/sessions/{session_id}/turns")


def _turn_job_path(vault: Vault, scenario_id: str, session_id: str, turn_id: str) -> Path:
    return _turn_jobs_dir(vault, scenario_id, session_id) / f"{turn_id}.json"


def _validate_ids(scenario_id: str, session_id: str, turn_id: str | None = None) -> None:
    if not is_locus_id(scenario_id):
        raise TurnJobError(f"Invalid scenario id: {scenario_id}")
    if not is_locus_id(session_id):
        raise TurnJobError(f"Invalid session id: {session_id}")
    if turn_id is not None and not is_locus_id(turn_id):
        raise TurnJobError(f"Invalid turn id: {turn_id}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

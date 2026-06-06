from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.ids import is_locus_id
from app.turn_loop import ChatCompletionClient, TurnPreparation, run_gm_post_turn
from app.vault import Vault, VaultError


class PostprocessJobError(VaultError):
    """Raised when post-turn job persistence or execution fails."""


ACTIVE_POSTPROCESS_JOB_STATUSES = frozenset({"queued", "running"})


def postprocess_job_id(turn: int) -> str:
    if not isinstance(turn, int) or isinstance(turn, bool) or turn < 0:
        raise PostprocessJobError("turn must be a non-negative integer")
    return f"post_turn_{turn:04d}"


def read_postprocess_job(vault: Vault, scenario_id: str, session_id: str, job_id: str) -> dict[str, Any]:
    _validate_ids(scenario_id, session_id, job_id)
    path = _postprocess_job_path(vault, scenario_id, session_id, job_id)
    if not path.is_file():
        raise PostprocessJobError(f"Postprocess job not found: {job_id}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PostprocessJobError(f"Invalid postprocess job JSON: {job_id}") from exc
    if not isinstance(payload, dict):
        raise PostprocessJobError("Postprocess job must be a JSON object")
    return payload


def find_active_postprocess_job(vault: Vault, scenario_id: str, session_id: str) -> dict[str, Any] | None:
    _validate_ids(scenario_id, session_id)
    directory = _postprocess_jobs_dir(vault, scenario_id, session_id)
    if not directory.is_dir():
        return None
    for path in sorted(directory.glob("post_turn_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and payload.get("status") in ACTIVE_POSTPROCESS_JOB_STATUSES:
            return payload
    return None


def start_postprocess_job(
    vault: Vault,
    *,
    scenario_id: str,
    session_id: str,
    user_message: str,
    assistant_content: str,
    prepared: TurnPreparation,
    state_model_client: ChatCompletionClient | None,
) -> dict[str, Any]:
    _validate_ids(scenario_id, session_id)
    job_id = postprocess_job_id(prepared.turn)
    now = _now_iso()
    payload: dict[str, Any] = {
        "job_id": job_id,
        "scenario_id": scenario_id,
        "session_id": session_id,
        "turn": prepared.turn,
        "status": "queued",
        "created_at": now,
        "updated_at": now,
        "started_at": None,
        "completed_at": None,
        "error": None,
        "result": None,
    }
    write_postprocess_job(vault, scenario_id, session_id, job_id, payload)
    thread = threading.Thread(
        target=_run_postprocess_job,
        kwargs={
            "vault": vault,
            "scenario_id": scenario_id,
            "session_id": session_id,
            "job_id": job_id,
            "user_message": user_message,
            "assistant_content": assistant_content,
            "prepared": prepared,
            "state_model_client": state_model_client,
        },
        daemon=True,
    )
    thread.start()
    return payload


def write_postprocess_job(
    vault: Vault,
    scenario_id: str,
    session_id: str,
    job_id: str,
    payload: dict[str, Any],
) -> None:
    _validate_ids(scenario_id, session_id, job_id)
    if not isinstance(payload, dict):
        raise PostprocessJobError("Postprocess job payload must be a JSON object")
    path = _postprocess_job_path(vault, scenario_id, session_id, job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        temp_path.write_text(raw, encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _run_postprocess_job(
    *,
    vault: Vault,
    scenario_id: str,
    session_id: str,
    job_id: str,
    user_message: str,
    assistant_content: str,
    prepared: TurnPreparation,
    state_model_client: ChatCompletionClient | None,
) -> None:
    _update_postprocess_job(vault, scenario_id, session_id, job_id, {"status": "running", "started_at": _now_iso()})
    try:
        result = run_gm_post_turn(
            vault,
            scenario_id=scenario_id,
            session_id=session_id,
            user_message=user_message,
            assistant_content=assistant_content,
            prepared=prepared,
            state_model_client=state_model_client,
        )
        _update_postprocess_job(
            vault,
            scenario_id,
            session_id,
            job_id,
            {
                "status": "completed",
                "completed_at": _now_iso(),
                "result": result,
                "error": None,
            },
        )
    except Exception as exc:
        _update_postprocess_job(
            vault,
            scenario_id,
            session_id,
            job_id,
            {
                "status": "failed",
                "completed_at": _now_iso(),
                "error": {"type": type(exc).__name__, "message": str(exc)},
            },
        )


def _update_postprocess_job(
    vault: Vault,
    scenario_id: str,
    session_id: str,
    job_id: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    payload = read_postprocess_job(vault, scenario_id, session_id, job_id)
    payload.update(updates)
    payload["updated_at"] = _now_iso()
    write_postprocess_job(vault, scenario_id, session_id, job_id, payload)
    return payload


def _postprocess_jobs_dir(vault: Vault, scenario_id: str, session_id: str) -> Path:
    return vault.resolve(f"rp/scenarios/{scenario_id}/sessions/{session_id}/postprocess")


def _postprocess_job_path(vault: Vault, scenario_id: str, session_id: str, job_id: str) -> Path:
    return _postprocess_jobs_dir(vault, scenario_id, session_id) / f"{job_id}.json"


def _validate_ids(scenario_id: str, session_id: str, job_id: str | None = None) -> None:
    if not is_locus_id(scenario_id):
        raise PostprocessJobError(f"Invalid scenario id: {scenario_id}")
    if not is_locus_id(session_id):
        raise PostprocessJobError(f"Invalid session id: {session_id}")
    if job_id is not None and not is_locus_id(job_id):
        raise PostprocessJobError(f"Invalid postprocess job id: {job_id}")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

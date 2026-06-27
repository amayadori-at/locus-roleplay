from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from app.turn_loop import TurnResult


def turn_result_payload(result: TurnResult) -> dict[str, Any]:
    return {
        "session_id": result.session_id,
        "scenario_id": result.scenario_id,
        "turn": result.turn,
        "assistant_content": result.assistant_content,
        "segments": [segment_payload(segment) for segment in result.segments],
        "state_updated": result.state_updated,
        "state_update_error": result.state_update_error,
        "memory_updated": result.memory_updated,
        "memory_update_error": result.memory_update_error,
        "memory_files": result.memory_files,
        "response_duration_ms": result.response_duration_ms,
        "timings_ms": result.timings_ms,
    }


def segment_payload(segment: object) -> dict[str, Any]:
    if is_dataclass(segment):
        return asdict(segment)
    if isinstance(segment, dict):
        return dict(segment)
    raise ValueError("turn result contains an unsupported segment")

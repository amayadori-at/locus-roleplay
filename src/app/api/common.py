from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class ApiResponse:
    status: int
    content_type: str
    body: bytes
    last_modified: float | None = None
    headers: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ApiStreamResponse:
    status: int
    content_type: str
    events: Iterable[bytes]


class ApiNotFound(Exception):
    pass


def _atomic_write(path: Path, content: str) -> None:
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


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


def _timeline_excerpt(content: str, limit: int = 80) -> str:
    compact = " ".join(content.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _json_response(payload: dict[str, Any], status: int = 200) -> ApiResponse:
    return ApiResponse(
        status=status,
        content_type="application/json; charset=utf-8",
        body=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
    )


_ERROR_CODES_BY_STATUS = {400: "bad_request", 404: "not_found", 409: "conflict"}


def _error_response(status: int, message: str) -> ApiResponse:
    return _json_response({"error": _ERROR_CODES_BY_STATUS.get(status, "error"), "message": message}, status=status)


def _sse_event(event: str, payload: dict[str, Any]) -> bytes:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {data}\n\n".encode("utf-8")


def _duration_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))

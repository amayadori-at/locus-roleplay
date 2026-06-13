from __future__ import annotations

import re
from typing import Any


REASONING_BLOCK_PATTERN = re.compile(r"<reasoning\b[^>]*>[\s\S]*?</reasoning>", re.IGNORECASE)
REASONING_BLOCK_WITH_TRAILING_NEWLINE_PATTERN = re.compile(
    r"<reasoning\b[^>]*>[\s\S]*?</reasoning>\r?\n?",
    re.IGNORECASE,
)


def strip_reasoning_blocks(content: str) -> str:
    if not isinstance(content, str):
        return ""
    return REASONING_BLOCK_PATTERN.sub("", content).strip()


def remove_reasoning_blocks(content: str) -> str:
    if not isinstance(content, str):
        return ""
    return REASONING_BLOCK_WITH_TRAILING_NEWLINE_PATTERN.sub("", content)


def sanitize_log_entries(entries: list[dict[str, Any]] | None, *, trim: bool = True) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        copy = dict(entry)
        content = copy.get("content")
        if isinstance(content, str):
            copy["content"] = strip_reasoning_blocks(content) if trim else remove_reasoning_blocks(content)
        sanitized.append(copy)
    return sanitized

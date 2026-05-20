from __future__ import annotations

import math
import re
import unicodedata
from typing import Any


MESSAGE_OVERHEAD_TOKENS = 4


def estimate_prompt_token_usage(
    messages: list[dict[str, str]],
    profile_data: dict[str, Any],
) -> dict[str, Any]:
    message_usage = []
    prompt_tokens = 0
    for index, message in enumerate(messages):
        role = message.get("role", "")
        content = message.get("content", "")
        role_tokens = estimate_text_tokens(role)
        content_tokens = estimate_text_tokens(content)
        total_tokens = MESSAGE_OVERHEAD_TOKENS + role_tokens + content_tokens
        prompt_tokens += total_tokens
        message_usage.append(
            {
                "index": index,
                "role": role,
                "content_tokens": content_tokens,
                "total_tokens": total_tokens,
            }
        )

    context_size = _optional_int(profile_data.get("context_size"))
    max_response_tokens = _optional_int(profile_data.get("max_tokens"))
    reserved_response_tokens = max_response_tokens or 0
    total_with_reserved_response = prompt_tokens + reserved_response_tokens
    remaining_context_tokens = None
    prompt_context_ratio = None
    total_context_ratio = None
    if context_size is not None:
        remaining_context_tokens = context_size - total_with_reserved_response
        prompt_context_ratio = round(prompt_tokens / context_size, 4)
        total_context_ratio = round(total_with_reserved_response / context_size, 4)

    return {
        "estimate": True,
        "tokenizer": "unicode_heuristic",
        "prompt_tokens": prompt_tokens,
        "message_overhead_tokens": MESSAGE_OVERHEAD_TOKENS,
        "messages": message_usage,
        "context_size": context_size,
        "max_response_tokens": max_response_tokens,
        "reserved_response_tokens": reserved_response_tokens,
        "total_with_reserved_response": total_with_reserved_response,
        "remaining_context_tokens": remaining_context_tokens,
        "prompt_context_ratio": prompt_context_ratio,
        "total_context_ratio": total_context_ratio,
    }


def estimate_text_tokens(text: str) -> int:
    if not text:
        return 0

    tokens = 0
    ascii_buffer = []
    for char in text:
        if char.isascii() and (char.isalnum() or char == "_"):
            ascii_buffer.append(char)
            continue
        if ascii_buffer:
            tokens += _estimate_ascii_word_tokens("".join(ascii_buffer))
            ascii_buffer = []
        if char.isspace():
            continue
        tokens += _estimate_non_ascii_or_symbol_tokens(char)
    if ascii_buffer:
        tokens += _estimate_ascii_word_tokens("".join(ascii_buffer))
    return max(1, tokens)


def _estimate_ascii_word_tokens(value: str) -> int:
    parts = [part for part in re.split(r"(_+)", value) if part]
    return sum(max(1, math.ceil(len(part) / 4)) for part in parts)


def _estimate_non_ascii_or_symbol_tokens(char: str) -> int:
    category = unicodedata.category(char)
    if category.startswith(("P", "S")):
        return 1
    if _is_cjk(char):
        return 1
    return max(1, math.ceil(len(char.encode("utf-8")) / 3))


def _is_cjk(char: str) -> bool:
    codepoint = ord(char)
    return (
        0x3040 <= codepoint <= 0x30FF
        or 0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
        or 0xFF00 <= codepoint <= 0xFFEF
    )


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None

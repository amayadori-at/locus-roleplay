from __future__ import annotations

from typing import Final


CHAT_ROLES: Final[frozenset[str]] = frozenset({"system", "user", "assistant", "tool"})
CONVERSATION_ROLES: Final[frozenset[str]] = frozenset({"user", "assistant"})


def is_chat_role(role: object) -> bool:
    return isinstance(role, str) and role in CHAT_ROLES


def is_conversation_role(role: object) -> bool:
    return isinstance(role, str) and role in CONVERSATION_ROLES

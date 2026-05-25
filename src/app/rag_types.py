from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RagDocument:
    source_path: str
    type: str
    title: str
    body: str
    metadata: dict[str, Any]
    chunk_id: str | None = None
    heading_path: list[str] | None = None


def document_key(document: RagDocument) -> str:
    return document_key_from_parts(document.source_path, document.chunk_id)


def document_key_from_parts(source_path: str, chunk_id: str | None) -> str:
    if chunk_id:
        return f"{source_path}#{chunk_id}"
    return source_path


def normalize_chunk_id(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def normalize_heading_path(value: object) -> list[str] | None:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    return None

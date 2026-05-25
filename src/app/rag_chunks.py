from __future__ import annotations

import re
from typing import Any

from app.rag_types import RagDocument


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_LOCUS_RAG_RE = re.compile(r"<locus-rag\b([^>]*)>(.*?)</locus-rag>", re.IGNORECASE | re.DOTALL)
_ATTR_RE = re.compile(r"([A-Za-z_:][A-Za-z0-9_:.-]*)\s*=\s*(\"([^\"]*)\"|'([^']*)')")


def chunk_rag_document(
    *,
    source_path: str,
    doc_type: str,
    title: str,
    body: str,
    metadata: dict[str, Any],
    chunkable: bool,
) -> list[RagDocument]:
    if not chunkable:
        return [
            RagDocument(
                source_path=source_path,
                type=doc_type,
                title=title,
                body=body.strip(),
                metadata=metadata,
            )
        ]
    return _chunk_lore_memory_document(
        source_path=source_path,
        doc_type=doc_type,
        title=title,
        body=body,
        metadata=metadata,
    )


def _chunk_lore_memory_document(
    *,
    source_path: str,
    doc_type: str,
    title: str,
    body: str,
    metadata: dict[str, Any],
) -> list[RagDocument]:
    locus_chunks, body_without_locus = _extract_locus_rag_chunks(
        source_path=source_path,
        doc_type=doc_type,
        title=title,
        body=body,
        metadata=metadata,
    )
    heading_chunks = _extract_heading_chunks(
        source_path=source_path,
        doc_type=doc_type,
        title=title,
        body=body_without_locus,
        metadata=metadata,
    )
    chunks = heading_chunks + locus_chunks
    if chunks:
        return chunks
    return [
        RagDocument(
            source_path=source_path,
            type=doc_type,
            title=title,
            body=body.strip(),
            metadata=_chunk_metadata(metadata, chunk_id="file", heading_path=[]),
            chunk_id="file",
            heading_path=[],
        )
    ]


def _extract_locus_rag_chunks(
    *,
    source_path: str,
    doc_type: str,
    title: str,
    body: str,
    metadata: dict[str, Any],
) -> tuple[list[RagDocument], str]:
    chunks: list[RagDocument] = []
    body_parts: list[str] = []
    cursor = 0
    ordinal = 1
    for match in _LOCUS_RAG_RE.finditer(body):
        body_parts.append(body[cursor : match.start()])
        body_parts.append("\n")
        cursor = match.end()
        content = match.group(2).strip()
        if not content:
            continue
        attrs = _parse_locus_rag_attrs(match.group(1))
        attr_id = attrs.get("id")
        chunk_id = f"locus:{attr_id}" if attr_id else f"locus:{ordinal:04d}"
        ordinal += 1
        attr_title = attrs.get("title")
        chunk_title = attr_title or attr_id or title
        heading_path = [chunk_title] if chunk_title else []
        chunk_metadata = _chunk_metadata(
            metadata,
            chunk_id=chunk_id,
            heading_path=heading_path,
            chunk_type="locus-rag",
            locus_attrs=attrs,
        )
        chunks.append(
            RagDocument(
                source_path=source_path,
                type=doc_type,
                title=chunk_title,
                body=content,
                metadata=chunk_metadata,
                chunk_id=chunk_id,
                heading_path=heading_path,
            )
        )
    body_parts.append(body[cursor:])
    return chunks, "".join(body_parts)


def _extract_heading_chunks(
    *,
    source_path: str,
    doc_type: str,
    title: str,
    body: str,
    metadata: dict[str, Any],
) -> list[RagDocument]:
    chunks: list[RagDocument] = []
    heading_stack: list[tuple[int, str]] = []
    current_title = title
    current_heading_path: list[str] = []
    current_chunk_id = "file"
    current_lines: list[str] = []
    heading_ordinal = 0
    saw_heading = False

    def flush() -> None:
        content = "\n".join(current_lines).strip()
        if not content:
            current_lines.clear()
            return
        chunks.append(
            RagDocument(
                source_path=source_path,
                type=doc_type,
                title=current_title,
                body=content,
                metadata=_chunk_metadata(metadata, chunk_id=current_chunk_id, heading_path=current_heading_path),
                chunk_id=current_chunk_id,
                heading_path=list(current_heading_path),
            )
        )
        current_lines.clear()

    for line in body.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            flush()
            saw_heading = True
            level = len(match.group(1))
            heading = match.group(2).strip()
            heading_stack = [(item_level, item_heading) for item_level, item_heading in heading_stack if item_level < level]
            heading_stack.append((level, heading))
            current_heading_path = [item_heading for _, item_heading in heading_stack]
            heading_ordinal += 1
            current_title = heading
            current_chunk_id = f"heading:{heading_ordinal:04d}:{_compact_heading_path(current_heading_path)}"
            continue
        current_lines.append(line)
    flush()

    if not saw_heading and not chunks:
        stripped = body.strip()
        if stripped:
            chunks.append(
                RagDocument(
                    source_path=source_path,
                    type=doc_type,
                    title=title,
                    body=stripped,
                    metadata=_chunk_metadata(metadata, chunk_id="file", heading_path=[]),
                    chunk_id="file",
                    heading_path=[],
                )
            )
    return chunks


def _chunk_metadata(
    metadata: dict[str, Any],
    *,
    chunk_id: str,
    heading_path: list[str],
    chunk_type: str = "heading",
    locus_attrs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = dict(metadata)
    result["chunk_id"] = chunk_id
    result["heading_path"] = list(heading_path)
    result["chunk_type"] = chunk_type
    if locus_attrs:
        result["locus_rag"] = dict(locus_attrs)
        if locus_attrs.get("id"):
            result["locus_rag_id"] = locus_attrs["id"]
        if locus_attrs.get("title"):
            result["locus_rag_title"] = locus_attrs["title"]
        result["tags"] = _merge_metadata_list(result.get("tags"), locus_attrs.get("tags"))
        result["keywords"] = _merge_metadata_list(result.get("keywords"), locus_attrs.get("keywords"))
    return result


def _parse_locus_rag_attrs(raw_attrs: str) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    for match in _ATTR_RE.finditer(raw_attrs):
        key = match.group(1).strip().lower()
        if key not in {"id", "title", "tags", "keywords"}:
            continue
        value = (match.group(3) if match.group(3) is not None else match.group(4)).strip()
        if key in {"tags", "keywords"}:
            attrs[key] = _comma_list(value)
        elif value:
            attrs[key] = value
    return attrs


def _comma_list(value: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in value.split(","):
        normalized = item.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _merge_metadata_list(base: object, extra: object) -> list[str]:
    values: list[str] = []
    for source in (base, extra):
        if isinstance(source, list):
            items = source
        elif isinstance(source, str):
            items = [source]
        else:
            items = []
        for item in items:
            if not isinstance(item, str):
                continue
            value = item.strip()
            if value and value not in values:
                values.append(value)
    return values


def _compact_heading_path(heading_path: list[str]) -> str:
    compact = "_".join(re.sub(r"\s+", "_", heading).strip("_") for heading in heading_path)
    compact = re.sub(r"[#\r\n]+", "", compact).strip("_")
    return compact or "section"

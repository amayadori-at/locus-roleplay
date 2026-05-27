from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.ids import is_locus_id
from app.rag_chunks import chunk_rag_document
from app.rag_types import RagDocument, document_key
from app.vault import Vault, VaultFileError


class RagDocumentError(Exception):
    pass


KEYWORD_TRIGGER_LIMIT = 4
KEYWORD_TRIGGER_MESSAGE_LIMIT = 8
DEFAULT_KEYWORD_TRIGGER_TOKEN_BUDGET = 1200


def list_available_mods(vault: Vault, scenario_id: str) -> list[dict[str, Any]]:
    """List lore files with mod: true in frontmatter."""
    if not is_locus_id(scenario_id):
        raise RagDocumentError(f"Invalid scenario id: {scenario_id}")
    base = vault.resolve(f"rp/scenarios/{scenario_id}")
    if not base.is_dir():
        return []
    lore_dir = base / "lore"
    if not lore_dir.is_dir():
        return []
    results: list[dict[str, Any]] = []
    for path in sorted(lore_dir.glob("*.md")):
        vault_relative = path.relative_to(vault.root).as_posix()
        scenario_relative = path.relative_to(base).as_posix()
        try:
            document = vault.load_markdown(vault_relative)
        except VaultFileError:
            continue
        metadata = dict(document.frontmatter)
        if metadata.get("mod") is not True:
            continue
        results.append({"path": scenario_relative, "title": document_title(path, metadata)})
    return results


def list_available_characters(vault: Vault, scenario_id: str) -> list[dict[str, Any]]:
    """List all character files available for pinning."""
    if not is_locus_id(scenario_id):
        raise RagDocumentError(f"Invalid scenario id: {scenario_id}")
    base = vault.resolve(f"rp/scenarios/{scenario_id}")
    if not base.is_dir():
        return []
    char_dir = base / "characters"
    if not char_dir.is_dir():
        return []
    results: list[dict[str, Any]] = []
    for path in sorted(char_dir.glob("*.md")):
        vault_relative = path.relative_to(vault.root).as_posix()
        scenario_relative = path.relative_to(base).as_posix()
        try:
            document = vault.load_markdown(vault_relative)
        except VaultFileError:
            continue
        metadata = dict(document.frontmatter)
        results.append({"path": scenario_relative, "title": document_title(path, metadata)})
    return results


def list_keyword_lore_documents(vault: Vault, scenario_id: str) -> tuple[list[RagDocument], list[str]]:
    """List lore files that define keyword triggers.

    Unlike normal RAG documents, keyword-triggered lore intentionally ignores
    frontmatter rag: false. keywords_enabled: false is the explicit opt-out.
    """
    if not is_locus_id(scenario_id):
        raise RagDocumentError(f"Invalid scenario id: {scenario_id}")
    base = vault.resolve(f"rp/scenarios/{scenario_id}")
    if not base.is_dir():
        raise RagDocumentError(f"Scenario directory does not exist: {scenario_id}")
    lore_dir = base / "lore"
    if not lore_dir.is_dir():
        return [], []

    documents: list[RagDocument] = []
    warnings: list[str] = []
    for path in sorted(lore_dir.glob("*.md")):
        relative = path.relative_to(vault.root).as_posix()
        scenario_relative = path.relative_to(base).as_posix()
        try:
            document = vault.load_markdown(relative)
        except VaultFileError as exc:
            raise RagDocumentError(f"Keyword lore markdown is unreadable: {scenario_relative}") from exc
        metadata = dict(document.frontmatter)
        if metadata.get("keywords_enabled") is False:
            continue
        keywords = _keyword_list(metadata.get("keywords"), source_path=scenario_relative)
        if not keywords:
            continue
        one_char = [keyword for keyword in keywords if len(keyword) == 1]
        if one_char:
            warnings.append(f"{scenario_relative}: 1-character keyword(s): {', '.join(one_char)}")
        documents.append(
            RagDocument(
                source_path=scenario_relative,
                type=document_type("lore", metadata),
                title=document_title(path, metadata),
                body=document.body.strip(),
                metadata={**metadata, "keywords": keywords},
            )
        )
    return documents, warnings


def keyword_trigger_messages(
    *,
    user_message: str,
    recent_log: list[dict[str, Any]] | None = None,
    limit: int = KEYWORD_TRIGGER_MESSAGE_LIMIT,
) -> list[str]:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        limit = KEYWORD_TRIGGER_MESSAGE_LIMIT
    messages: list[str] = []
    for entry in recent_log or []:
        content = entry.get("content")
        if isinstance(content, str) and content.strip():
            messages.append(content)
    if isinstance(user_message, str) and user_message.strip():
        messages.append(user_message)
    return messages[-limit:]


def keyword_triggered_lore_results(
    vault: Vault,
    scenario_id: str,
    *,
    user_message: str,
    recent_log: list[dict[str, Any]] | None = None,
    limit: int = KEYWORD_TRIGGER_LIMIT,
    exclude_paths: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    documents, warnings = list_keyword_lore_documents(vault, scenario_id)
    messages = [message.lower() for message in keyword_trigger_messages(user_message=user_message, recent_log=recent_log)]
    if not documents or not messages:
        return [], warnings
    excluded = exclude_paths or set()

    matched_documents: list[tuple[RagDocument, list[str]]] = []
    for document in documents:
        if document.source_path in excluded:
            continue
        keywords = _keyword_list(document.metadata.get("keywords"), source_path=document.source_path)
        matched = [keyword for keyword in keywords if any(keyword.lower() in message for message in messages)]
        if not matched:
            continue
        matched_documents.append((document, matched))
    matched_documents.sort(key=lambda item: (-_priority(item[0].metadata), item[0].source_path))
    matched_documents = matched_documents[:limit]

    results: list[dict[str, Any]] = []
    for document, matched in matched_documents:
        file_priority = _priority(document.metadata)
        chunk_enabled = document.metadata.get("chunk_enabled") is not False
        if chunk_enabled:
            chunks = chunk_rag_document(
                source_path=document.source_path,
                doc_type=document.type,
                title=document.title,
                body=document.body,
                metadata=document.metadata,
                chunkable=True,
            )
            for chunk in chunks:
                if not _chunk_keywords_match(chunk, messages):
                    continue
                chunk_priority = _priority(chunk.metadata)
                results.append(
                    {
                        "source_path": chunk.source_path,
                        "chunk_id": chunk.chunk_id,
                        "heading_path": chunk.heading_path or [],
                        "type": chunk.type,
                        "title": chunk.title,
                        "score": chunk_priority,
                        "content": chunk.body.strip(),
                        "metadata": chunk.metadata,
                        "matched_terms": matched,
                        "matched_keywords": matched,
                        "match_type": "keyword",
                        "priority": chunk_priority,
                    }
                )
        else:
            results.append(
                {
                    "source_path": document.source_path,
                    "type": document.type,
                    "title": document.title,
                    "score": file_priority,
                    "content": document.body.strip(),
                    "metadata": document.metadata,
                    "matched_terms": matched,
                    "matched_keywords": matched,
                    "match_type": "keyword",
                    "priority": file_priority,
                }
            )
    return results, warnings


def load_scenario_file(vault: Vault, scenario_id: str, scenario_relative_path: str) -> RagDocument | None:
    """Load a single scenario file as a RagDocument. Returns None if not found."""
    if "\\" in scenario_relative_path:
        return None
    parts = scenario_relative_path.split("/")
    if any(p in ("", ".", "..") for p in parts):
        return None
    vault_relative = f"rp/scenarios/{scenario_id}/{scenario_relative_path}"
    path = vault.resolve(vault_relative)
    try:
        document = vault.load_markdown(vault_relative)
    except VaultFileError:
        return None
    metadata = dict(document.frontmatter)
    folder = parts[0] if len(parts) > 1 else ""
    return RagDocument(
        source_path=scenario_relative_path,
        type=document_type(folder, metadata),
        title=document_title(path, metadata),
        body=document.body.strip(),
        metadata=metadata,
    )


def list_rag_documents(
    vault: Vault,
    scenario_id: str,
    *,
    sources: set[str] | None = None,
) -> list[RagDocument]:
    if not is_locus_id(scenario_id):
        raise RagDocumentError(f"Invalid scenario id: {scenario_id}")
    allowed_sources = sources or {"memory", "lore", "characters"}
    base = vault.resolve(f"rp/scenarios/{scenario_id}")
    if not base.is_dir():
        raise RagDocumentError(f"Scenario directory does not exist: {scenario_id}")

    documents: list[RagDocument] = []
    if "memory" in allowed_sources:
        documents.extend(documents_under(vault, base, "memory", recursive=True))
    if "lore" in allowed_sources:
        documents.extend(documents_under(vault, base, "lore", recursive=False))
    if "characters" in allowed_sources:
        documents.extend(documents_under(vault, base, "characters", recursive=False))
    return documents


def build_rag_query(
    *,
    user_message: str,
    recent_log: list[dict[str, Any]] | None = None,
    state: dict[str, Any] | None = None,
) -> str:
    parts = [user_message]
    for entry in (recent_log or [])[-6:]:
        content = entry.get("content")
        if isinstance(content, str):
            parts.append(content)
    if state:
        parts.append(json.dumps(state, ensure_ascii=False, sort_keys=True))
    return "\n".join(part for part in parts if part)


def documents_under(vault: Vault, base: Path, folder: str, *, recursive: bool) -> list[RagDocument]:
    directory = base / folder
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise RagDocumentError(f"RAG source is not a directory: {folder}")

    pattern = "**/*.md" if recursive else "*.md"
    documents: list[RagDocument] = []
    for path in sorted(directory.glob(pattern)):
        relative = path.relative_to(vault.root).as_posix()
        scenario_relative = path.relative_to(base).as_posix()
        try:
            document = vault.load_markdown(relative)
        except VaultFileError as exc:
            raise RagDocumentError(f"RAG markdown is unreadable: {scenario_relative}") from exc
        metadata = dict(document.frontmatter)
        if metadata.get("rag") is False:
            continue
        if metadata.get("keywords_enabled") is True:
            continue  # handled exclusively by keyword trigger pipeline
        documents.extend(
            chunk_rag_document(
                source_path=scenario_relative,
                doc_type=document_type(folder, metadata),
                title=document_title(path, metadata),
                body=document.body,
                metadata=metadata,
                chunkable=folder in {"memory", "lore"},
            )
        )
    return documents


def document_type(folder: str, metadata: dict[str, Any]) -> str:
    value = metadata.get("type")
    if isinstance(value, str) and value.strip():
        return value
    if folder == "characters":
        return "character"
    return folder


def document_title(path: Path, metadata: dict[str, Any]) -> str:
    for field in ("title", "name", "id"):
        value = metadata.get(field)
        if isinstance(value, str) and value.strip():
            return value
    return path.stem


def _keyword_list(value: object, *, source_path: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise RagDocumentError(f"{source_path}: keywords must be a list")
    keywords: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise RagDocumentError(f"{source_path}: keywords must contain strings only")
        keyword = item.strip()
        if not keyword:
            raise RagDocumentError(f"{source_path}: keywords must not contain empty strings")
        if keyword not in seen:
            seen.add(keyword)
            keywords.append(keyword)
    return keywords


def _chunk_keywords_match(chunk: "RagDocument", messages: list[str]) -> bool:
    """Return True if this chunk should be included based on its own keywords.

    locus-rag chunks with keywords are only included when at least one keyword
    matches the messages. Chunks without keywords (heading chunks, or locus-rag
    chunks that omit keywords) are always included.

    Uses metadata["locus_rag"]["keywords"] (chunk-own) rather than metadata["keywords"]
    (which merges file-level frontmatter keywords and would cause false positives).
    """
    if chunk.metadata.get("chunk_type") != "locus-rag":
        return True
    locus_data = chunk.metadata.get("locus_rag")
    if not isinstance(locus_data, dict):
        return True
    chunk_keywords = locus_data.get("keywords")
    if not chunk_keywords:
        return True
    return any(kw.lower() in message for kw in chunk_keywords for message in messages)


def _priority(metadata: dict[str, Any]) -> int | float:
    value = metadata.get("priority")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return 0

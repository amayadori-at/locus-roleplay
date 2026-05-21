from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.ids import is_locus_id
from app.rag_documents import RagDocument, RagDocumentError, document_title, document_type, list_rag_documents
from app.vault import Vault, VaultError, VaultFileError


class RagIndexError(VaultError):
    pass


RAG_INDEX_VERSION = 2


def rebuild_rag_index(vault: Vault, scenario_id: str) -> dict[str, Any]:
    payload = update_rag_index(vault, scenario_id)
    payload["full_rebuild_compatible"] = True
    return payload


def update_rag_index(vault: Vault, scenario_id: str) -> dict[str, Any]:
    if not is_locus_id(scenario_id):
        raise RagIndexError(f"Invalid scenario id: {scenario_id}")
    base = vault.resolve(f"rp/scenarios/{scenario_id}")
    if not base.is_dir():
        raise RagIndexError(f"Scenario directory does not exist: {scenario_id}")

    previous = read_rag_index(vault, scenario_id)
    previous_by_path = _previous_documents_by_path(previous)
    candidates = _candidate_markdown_paths(vault, scenario_id)
    indexed_documents: list[dict[str, Any]] = []
    reused_count = 0
    indexed_count = 0
    skipped_count = 0
    changed_paths: list[str] = []
    skipped_paths: list[str] = []

    for candidate in candidates:
        previous_item = previous_by_path.get(candidate.source_path)
        if previous_item and _index_item_matches_stat(previous_item, candidate.stat):
            indexed_documents.append(previous_item)
            reused_count += 1
            continue
        indexed = _index_candidate(vault, scenario_id, candidate)
        if indexed is None:
            skipped_count += 1
            skipped_paths.append(candidate.source_path)
            continue
        indexed_documents.append(indexed)
        indexed_count += 1
        changed_paths.append(candidate.source_path)

    current_paths = {candidate.source_path for candidate in candidates}
    removed_paths = sorted(path for path in previous_by_path if path not in current_paths)
    payload = {
        "version": RAG_INDEX_VERSION,
        "scenario_id": scenario_id,
        "indexed_at": _now_iso(),
        "document_count": len(indexed_documents),
        "documents": indexed_documents,
        "incremental": {
            "reused_count": reused_count,
            "indexed_count": indexed_count,
            "skipped_count": skipped_count,
            "removed_count": len(removed_paths),
            "changed_paths": changed_paths,
            "removed_paths": removed_paths,
            "skipped_paths": skipped_paths,
        },
    }
    _write_index_payload(vault, scenario_id, payload)
    clear_rag_stale_marker(vault, scenario_id)
    return payload


def read_rag_index(vault: Vault, scenario_id: str) -> dict[str, Any] | None:
    if not is_locus_id(scenario_id):
        raise RagIndexError(f"Invalid scenario id: {scenario_id}")
    path = vault.resolve(_rag_index_path(scenario_id))
    if not path.exists():
        return None
    raw = vault.load_json(_rag_index_path(scenario_id))
    if not isinstance(raw, dict):
        raise RagIndexError("RAG index root must be a JSON object")
    return raw


def rag_index_rebuild_needed(vault: Vault, scenario_id: str, index: dict[str, Any] | None = None) -> bool:
    index = read_rag_index(vault, scenario_id) if index is None else index
    if not index:
        return True
    if index.get("version") != RAG_INDEX_VERSION:
        return True
    indexed = index.get("documents")
    if not isinstance(indexed, list):
        return True
    indexed_by_path = {item.get("source_path"): item for item in indexed if isinstance(item, dict)}
    current_candidates = _candidate_markdown_paths(vault, scenario_id)
    if set(indexed_by_path) - {candidate.source_path for candidate in current_candidates}:
        return True
    for candidate in current_candidates:
        indexed_document = indexed_by_path.get(candidate.source_path)
        if not isinstance(indexed_document, dict):
            document = _load_candidate_document(vault, scenario_id, candidate)
            if document is None:
                continue
            return True
        if not _index_item_matches_stat(indexed_document, candidate.stat):
            document = _load_candidate_document(vault, scenario_id, candidate)
            if document is None:
                return True
            return True
    return False


def clear_rag_stale_marker(vault: Vault, scenario_id: str) -> bool:
    stale_path = vault.resolve("rp/_cache/rag/stale.json")
    if not stale_path.exists():
        return False
    try:
        raw = vault.load_json("rp/_cache/rag/stale.json")
    except VaultError:
        return False
    if isinstance(raw, dict) and raw.get("scenario_id") == scenario_id:
        stale_path.unlink()
        return True
    return False


def rag_index_path(scenario_id: str) -> str:
    return _rag_index_path(scenario_id)


def _list_documents(vault: Vault, scenario_id: str) -> list[RagDocument]:
    try:
        return list_rag_documents(vault, scenario_id)
    except RagDocumentError as exc:
        raise RagIndexError(str(exc)) from exc


class _Candidate:
    def __init__(self, source_path: str, path: Path, stat: Any, folder: str) -> None:
        self.source_path = source_path
        self.path = path
        self.stat = stat
        self.folder = folder


def _candidate_markdown_paths(vault: Vault, scenario_id: str) -> list[_Candidate]:
    base = vault.resolve(f"rp/scenarios/{scenario_id}")
    candidates: list[_Candidate] = []
    for folder, recursive in (("memory", True), ("lore", False), ("characters", False)):
        directory = base / folder
        if not directory.exists():
            continue
        if not directory.is_dir():
            raise RagIndexError(f"RAG source is not a directory: {folder}")
        pattern = "**/*.md" if recursive else "*.md"
        for path in sorted(directory.glob(pattern)):
            if not path.is_file():
                continue
            candidates.append(
                _Candidate(
                    source_path=path.relative_to(base).as_posix(),
                    path=path,
                    stat=path.stat(),
                    folder=folder,
                )
            )
    return candidates


def _previous_documents_by_path(index: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(index, dict) or index.get("version") != RAG_INDEX_VERSION:
        return {}
    documents = index.get("documents")
    if not isinstance(documents, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for item in documents:
        if not isinstance(item, dict):
            continue
        source_path = item.get("source_path")
        if isinstance(source_path, str):
            result[source_path] = item
    return result


def _index_item_matches_stat(item: dict[str, Any], stat: Any) -> bool:
    return item.get("size") == stat.st_size and item.get("mtime_ns") == stat.st_mtime_ns


def _load_candidate_document(vault: Vault, scenario_id: str, candidate: _Candidate) -> RagDocument | None:
    relative = f"rp/scenarios/{scenario_id}/{candidate.source_path}"
    try:
        document = vault.load_markdown(relative)
    except VaultFileError as exc:
        raise RagIndexError(f"RAG markdown is unreadable: {candidate.source_path}") from exc
    metadata = dict(document.frontmatter)
    if metadata.get("rag") is False:
        return None
    return RagDocument(
        source_path=candidate.source_path,
        type=document_type(candidate.folder, metadata),
        title=document_title(candidate.path, metadata),
        body=document.body.strip(),
        metadata=metadata,
    )


def _index_candidate(vault: Vault, scenario_id: str, candidate: _Candidate) -> dict[str, Any] | None:
    document = _load_candidate_document(vault, scenario_id, candidate)
    if document is None:
        return None
    return _index_document(vault, scenario_id, document, path=candidate.path, stat=candidate.stat)


def _index_document(vault: Vault, scenario_id: str, document: RagDocument, *, path: Path | None = None, stat: Any | None = None) -> dict[str, Any]:
    path = path or vault.resolve(f"rp/scenarios/{scenario_id}/{document.source_path}")
    raw = path.read_bytes()
    stat = stat or path.stat()
    return {
        "source_path": document.source_path,
        "type": document.type,
        "title": document.title,
        "metadata": document.metadata,
        "body": document.body,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "content_hash": hashlib.sha256(raw).hexdigest(),
    }


def _write_index_payload(vault: Vault, scenario_id: str, payload: dict[str, Any]) -> None:
    path = vault.resolve(_rag_index_path(scenario_id))
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _rag_index_path(scenario_id: str) -> str:
    return f"rp/_cache/rag/{scenario_id}.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

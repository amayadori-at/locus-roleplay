from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.ids import is_locus_id
from app.rag_documents import RagDocument, RagDocumentError, list_rag_documents
from app.vault import Vault, VaultError


class RagIndexError(VaultError):
    pass


RAG_INDEX_VERSION = 1


def rebuild_rag_index(vault: Vault, scenario_id: str) -> dict[str, Any]:
    documents = _list_documents(vault, scenario_id)
    indexed_documents = [_index_document(vault, scenario_id, document) for document in documents]
    payload = {
        "version": RAG_INDEX_VERSION,
        "scenario_id": scenario_id,
        "indexed_at": _now_iso(),
        "document_count": len(indexed_documents),
        "documents": indexed_documents,
    }
    path = vault.resolve(_rag_index_path(scenario_id))
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
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
    indexed = index.get("documents")
    if not isinstance(indexed, list):
        return True
    indexed_by_path = {item.get("source_path"): item for item in indexed if isinstance(item, dict)}
    current_documents = _list_documents(vault, scenario_id)
    if set(indexed_by_path) != {document.source_path for document in current_documents}:
        return True
    for document in current_documents:
        indexed_document = indexed_by_path.get(document.source_path)
        if not isinstance(indexed_document, dict):
            return True
        current = _index_document(vault, scenario_id, document)
        for field in ("size", "mtime_ns", "content_hash"):
            if indexed_document.get(field) != current[field]:
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


def _index_document(vault: Vault, scenario_id: str, document: RagDocument) -> dict[str, Any]:
    path = vault.resolve(f"rp/scenarios/{scenario_id}/{document.source_path}")
    raw = path.read_bytes()
    stat = path.stat()
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


def _rag_index_path(scenario_id: str) -> str:
    return f"rp/_cache/rag/{scenario_id}.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

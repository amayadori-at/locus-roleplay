from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.embedding import EmbeddingConfig, EmbeddingError, embed_texts, get_embedding_config
from app.ids import is_locus_id
from app.rag_documents import RagDocument, RagDocumentError, list_rag_documents
from app.vault import Vault, VaultError


class RagVectorError(VaultError):
    pass


VECTOR_INDEX_VERSION = 1


def build_vector_index(
    vault: Vault,
    scenario_id: str,
    config: EmbeddingConfig | None = None,
) -> dict[str, Any]:
    """Compute embeddings for all RAG documents and save to the vector index cache."""
    if config is None:
        config = get_embedding_config()
    if not config.enabled:
        raise EmbeddingError("Embedding is not configured")

    documents = _list_documents(vault, scenario_id)
    texts = [_embedding_text(document) for document in documents]
    embeddings = embed_texts(texts, config)

    indexed: list[dict[str, Any]] = []
    for document, embedding in zip(documents, embeddings):
        indexed.append({"source_path": document.source_path, "embedding": embedding})

    payload: dict[str, Any] = {
        "version": VECTOR_INDEX_VERSION,
        "scenario_id": scenario_id,
        "model": config.model,
        "indexed_at": _now_iso(),
        "document_count": len(indexed),
        "documents": indexed,
    }
    path = vault.resolve(_vector_index_path(scenario_id))
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return payload


def read_vector_index(vault: Vault, scenario_id: str) -> dict[str, Any] | None:
    """Return the cached vector index, or None if it does not exist or is unreadable."""
    if not is_locus_id(scenario_id):
        raise RagVectorError(f"Invalid scenario id: {scenario_id}")
    path = vault.resolve(_vector_index_path(scenario_id))
    if not path.exists():
        return None
    try:
        raw = vault.load_json(_vector_index_path(scenario_id))
    except VaultError:
        return None
    return raw if isinstance(raw, dict) else None


def vector_index_rebuild_needed(
    vault: Vault,
    scenario_id: str,
    config: EmbeddingConfig,
    index: dict[str, Any] | None = None,
) -> bool:
    """Return True when the vector index is absent, stale, or built with a different model."""
    if index is None:
        index = read_vector_index(vault, scenario_id)
    if not index:
        return True
    if index.get("version") != VECTOR_INDEX_VERSION:
        return True
    if index.get("model") != config.model:
        return True
    indexed = index.get("documents")
    if not isinstance(indexed, list):
        return True
    indexed_paths = {item.get("source_path") for item in indexed if isinstance(item, dict)}
    current_paths = {doc.source_path for doc in _list_documents(vault, scenario_id)}
    return indexed_paths != current_paths


def vector_index_path(scenario_id: str) -> str:
    return _vector_index_path(scenario_id)


def embedding_text(document: RagDocument) -> str:
    return _embedding_text(document)


def _list_documents(vault: Vault, scenario_id: str) -> list[RagDocument]:
    try:
        return list_rag_documents(vault, scenario_id)
    except RagDocumentError as exc:
        raise RagVectorError(str(exc)) from exc


def _embedding_text(document: RagDocument) -> str:
    parts = [document.title, document.body]
    return "\n".join(part for part in parts if part).strip()[:4000]


def _vector_index_path(scenario_id: str) -> str:
    return f"rp/_cache/rag/{scenario_id}_vectors.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

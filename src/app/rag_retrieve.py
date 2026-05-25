from __future__ import annotations

import json
import re
from typing import Any

from app.embedding import EmbeddingConfig, EmbeddingError, cosine_similarity, embed_texts, get_embedding_config
from app.ids import is_locus_id
from app.rag_documents import RagDocumentError, list_rag_documents
from app.rag_format import result_budget_type
from app.rag_index import RAG_INDEX_VERSION, index_item_to_document, rag_index_rebuild_needed, read_rag_index
from app.rag_types import RagDocument, document_key, document_key_from_parts
from app.rag_vectors import VECTOR_INDEX_VERSION, embedding_text, read_vector_index
from app.vault import Vault, VaultError


class RagRetrieveError(VaultError):
    """Raised when deterministic RAG retrieval fails."""


# Minimum cosine similarity to treat a vector-only match as a candidate
VECTOR_MATCH_THRESHOLD = 0.55
# Score assigned to a vector-only hit at threshold=1.0 (scales down toward threshold)
VECTOR_ONLY_MAX_SCORE = 40


def retrieve_context(
    vault: Vault,
    *,
    scenario_id: str,
    query: str,
    limit: int = 6,
    sources: list[str] | tuple[str, ...] | None = None,
    embedding_config: EmbeddingConfig | None = None,
    exclude_paths: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Retrieve relevant documents using keyword search, optionally blended with vector search."""
    if not is_locus_id(scenario_id):
        raise RagRetrieveError(f"Invalid scenario id: {scenario_id}")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise RagRetrieveError("RAG limit must be a non-negative integer")
    if limit == 0:
        return []

    terms = query_terms(query)
    allowed_sources = set(sources or ["memory", "lore", "characters"])
    documents = _fresh_index_documents(vault, scenario_id, sources=allowed_sources)
    if documents is None:
        documents = _list_documents(vault, scenario_id, sources=allowed_sources)

    if exclude_paths:
        documents = [doc for doc in documents if doc.source_path not in exclude_paths]

    if not terms and not documents:
        return []

    vector_sims = try_vector_similarities(vault, scenario_id, query, documents, embedding_config)

    if vector_sims is not None:
        scored = score_documents_hybrid(documents, terms, vector_sims)
    else:
        if not terms:
            return []
        scored = [_score_document(document, terms) for document in documents]

    results = [result for result in scored if result["score"] > 0]
    results.sort(key=lambda item: (-item["score"], item["source_path"], str(item.get("chunk_id") or "")))
    return results[:limit]


def query_terms(query: str) -> list[str]:
    if not isinstance(query, str):
        return []
    raw_terms: list[str] = []
    for match in re.findall(r"[A-Za-z0-9_]{2,}|[ぁ-んァ-ヶ一-龠ー]{2,}", query.lower()):
        raw_terms.append(match)
        if re.fullmatch(r"[ぁ-んァ-ヶ一-龠ー]+", match):
            raw_terms.extend(part for part in re.split(r"[のをにへでとがはもやか、。・]+", match) if len(part) >= 2)
            raw_terms.extend(_japanese_ngrams(match))
    seen: set[str] = set()
    terms: list[str] = []
    for term in raw_terms:
        if term not in seen:
            seen.add(term)
            terms.append(term)
    return terms[:80]


def try_vector_similarities(
    vault: Vault,
    scenario_id: str,
    query: str,
    documents: list[RagDocument],
    config: EmbeddingConfig | None,
) -> dict[str, float] | None:
    """Return {document_key: cosine_similarity} mapping, or None if embedding is unavailable/failed."""
    if config is None:
        config = get_embedding_config()
    if not config.enabled or not documents:
        return None

    index = read_vector_index(vault, scenario_id)
    if not index or index.get("model") != config.model or index.get("version") != VECTOR_INDEX_VERSION:
        return None

    indexed_vecs: dict[str, list[float]] = {}
    for item in index.get("documents", []):
        if isinstance(item, dict):
            sp = item.get("source_path")
            chunk_id = item.get("chunk_id")
            emb = item.get("embedding")
            if isinstance(sp, str) and isinstance(emb, list):
                indexed_vecs[document_key_from_parts(sp, chunk_id if isinstance(chunk_id, str) else None)] = emb

    if not all(document_key(doc) in indexed_vecs for doc in documents):
        return None

    try:
        query_emb = embed_texts([query[:2000]], config)[0]
    except EmbeddingError:
        return None

    return {document_key(doc): cosine_similarity(query_emb, indexed_vecs[document_key(doc)]) for doc in documents}


def score_documents_hybrid(
    documents: list[RagDocument],
    terms: list[str],
    vector_sims: dict[str, float],
) -> list[dict[str, Any]]:
    """Score documents using both keyword matching and vector similarity."""
    results: list[dict[str, Any]] = []
    for document in documents:
        keyword_result = _score_document(document, terms)
        keyword_score = keyword_result["score"]
        v_sim = vector_sims.get(document_key(document), 0.0)

        if keyword_score > 0:
            boost = max(0.0, v_sim) * keyword_score * 0.4
            combined = keyword_score + boost
        elif v_sim >= VECTOR_MATCH_THRESHOLD:
            combined = (v_sim - VECTOR_MATCH_THRESHOLD) / (1.0 - VECTOR_MATCH_THRESHOLD) * VECTOR_ONLY_MAX_SCORE
            keyword_result = {**keyword_result, "content": _excerpt(document.body, []), "matched_terms": []}
        else:
            combined = 0.0

        results.append({**keyword_result, "score": combined, "vector_similarity": round(v_sim, 4)})
    return results


def _list_documents(vault: Vault, scenario_id: str, *, sources: set[str]) -> list[RagDocument]:
    try:
        return list_rag_documents(vault, scenario_id, sources=sources)
    except RagDocumentError as exc:
        raise RagRetrieveError(str(exc)) from exc


def _japanese_ngrams(value: str) -> list[str]:
    terms: list[str] = []
    upper = min(6, len(value))
    for size in range(2, upper + 1):
        for index in range(0, len(value) - size + 1):
            terms.append(value[index : index + size])
    return terms


def _fresh_index_documents(vault: Vault, scenario_id: str, *, sources: set[str]) -> list[RagDocument] | None:
    try:
        index = read_rag_index(vault, scenario_id)
    except VaultError:
        return None
    if not index or index.get("version") != RAG_INDEX_VERSION:
        return None
    try:
        if rag_index_rebuild_needed(vault, scenario_id, index):
            return None
    except VaultError:
        return None

    indexed = index.get("documents")
    if not isinstance(indexed, list):
        return None
    documents: list[RagDocument] = []
    for item in indexed:
        if not isinstance(item, dict):
            return None
        source_path = item.get("source_path")
        if not isinstance(source_path, str):
            return None
        source_folder = _source_folder(source_path)
        if source_folder is None:
            return None
        if source_folder not in sources:
            continue
        document = index_item_to_document(item, source_folder=source_folder)
        if document is None:
            return None
        documents.append(document)
    return documents


def _source_folder(source_path: str) -> str | None:
    if source_path.startswith("/") or "\\" in source_path:
        return None
    parts = source_path.split("/")
    if not parts or any(part in {"", ".", ".."} for part in parts):
        return None
    folder = parts[0]
    if folder in {"memory", "lore", "characters"}:
        return folder
    return None


def _score_document(document: RagDocument, terms: list[str]) -> dict[str, Any]:
    searchable = _searchable_text(document).lower()
    matched_terms = [term for term in terms if term in searchable]
    if not matched_terms:
        return {
            "source_path": document.source_path,
            "chunk_id": document.chunk_id,
            "heading_path": document.heading_path or [],
            "type": document.type,
            "title": document.title,
            "score": 0,
            "content": "",
            "metadata": document.metadata,
            "matched_terms": [],
        }
    score = len(matched_terms) * 10
    score += _metadata_match_score(document.metadata, matched_terms)
    priority = document.metadata.get("priority")
    if isinstance(priority, (int, float)) and not isinstance(priority, bool):
        score += priority
    content = document.body.strip() if result_budget_type({"type": document.type, "source_path": document.source_path}) == "character" else _excerpt(document.body, matched_terms)
    return {
        "source_path": document.source_path,
        "chunk_id": document.chunk_id,
        "heading_path": document.heading_path or [],
        "type": document.type,
        "title": document.title,
        "score": score,
        "content": content,
        "metadata": document.metadata,
        "matched_terms": matched_terms,
    }


def _searchable_text(document: RagDocument) -> str:
    metadata_text = json.dumps(document.metadata, ensure_ascii=False, sort_keys=True)
    if result_budget_type({"type": document.type, "source_path": document.source_path}) == "character":
        return "\n".join(part for part in (document.title, metadata_text) if part)
    return "\n".join(part for part in (document.body, document.title, metadata_text) if part)


def _metadata_match_score(metadata: dict[str, Any], matched_terms: list[str]) -> int:
    score = 0
    for field in ("tags", "characters", "locations", "topics"):
        value = metadata.get(field)
        values = value if isinstance(value, list) else [value]
        haystack = " ".join(str(item).lower() for item in values if item is not None)
        score += sum(5 for term in matched_terms if term in haystack)
    return score


def _excerpt(body: str, matched_terms: list[str], limit: int = 900) -> str:
    text = " ".join(body.split())
    if len(text) <= limit:
        return text
    first_match = min((text.lower().find(term) for term in matched_terms if term in text.lower()), default=0)
    start = max(0, first_match - 120)
    end = min(len(text), start + limit)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"


def embedding_text_for_document(document: RagDocument) -> str:
    return embedding_text(document)

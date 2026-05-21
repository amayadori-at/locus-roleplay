from __future__ import annotations

from typing import Any

from app.embedding import EmbeddingConfig, embed_texts
from app.rag_documents import (
    DEFAULT_KEYWORD_TRIGGER_TOKEN_BUDGET,
    KEYWORD_TRIGGER_LIMIT,
    KEYWORD_TRIGGER_MESSAGE_LIMIT,
    RagDocument,
    RagDocumentError,
    build_rag_query as _build_rag_query,
    keyword_trigger_messages as _keyword_trigger_messages,
    keyword_triggered_lore_results as _keyword_triggered_lore_results,
    list_available_characters as _list_available_characters,
    list_available_mods as _list_available_mods,
    list_keyword_lore_documents as _list_keyword_lore_documents,
    list_rag_documents as _list_rag_documents,
    load_scenario_file as _load_scenario_file,
)
from app.rag_format import (
    DEFAULT_RAG_TOKEN_BUDGET,
    DEFAULT_RAG_TYPE_TOKEN_BUDGETS,
    budget_rag_results,
    format_rag_results,
)
from app.rag_index import (
    RagIndexError,
    clear_rag_stale_marker as _clear_rag_stale_marker,
    rag_index_rebuild_needed as _rag_index_rebuild_needed,
    read_rag_index as _read_rag_index,
    rebuild_rag_index as _rebuild_rag_index,
)
import app.rag_retrieve as _rag_retrieve
from app.rag_retrieve import (
    VECTOR_MATCH_THRESHOLD,
    VECTOR_ONLY_MAX_SCORE,
    RagRetrieveError,
    embedding_text_for_document as _retrieve_embedding_text,
    query_terms as _retrieve_query_terms,
    retrieve_context as _retrieve_context,
    score_documents_hybrid as _retrieve_score_documents_hybrid,
    try_vector_similarities as _retrieve_try_vector_similarities,
)
from app.rag_vectors import (
    RagVectorError,
    build_vector_index as _build_vector_index,
    read_vector_index as _read_vector_index,
    vector_index_rebuild_needed as _vector_index_rebuild_needed,
)
import app.rag_vectors as _rag_vectors
from app.vault import Vault, VaultError


class RagError(VaultError):
    """Raised when deterministic RAG retrieval fails."""


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
    try:
        _rag_retrieve.embed_texts = embed_texts
        return _retrieve_context(
            vault,
            scenario_id=scenario_id,
            query=query,
            limit=limit,
            sources=sources,
            embedding_config=embedding_config,
            exclude_paths=exclude_paths,
        )
    except RagRetrieveError as exc:
        raise RagError(str(exc)) from exc


def list_available_mods(vault: Vault, scenario_id: str) -> list[dict[str, Any]]:
    try:
        return _list_available_mods(vault, scenario_id)
    except RagDocumentError as exc:
        raise RagError(str(exc)) from exc


def list_available_characters(vault: Vault, scenario_id: str) -> list[dict[str, Any]]:
    try:
        return _list_available_characters(vault, scenario_id)
    except RagDocumentError as exc:
        raise RagError(str(exc)) from exc


def load_scenario_file(vault: Vault, scenario_id: str, scenario_relative_path: str) -> RagDocument | None:
    try:
        return _load_scenario_file(vault, scenario_id, scenario_relative_path)
    except RagDocumentError as exc:
        raise RagError(str(exc)) from exc


def list_rag_documents(
    vault: Vault,
    scenario_id: str,
    *,
    sources: set[str] | None = None,
) -> list[RagDocument]:
    try:
        return _list_rag_documents(vault, scenario_id, sources=sources)
    except RagDocumentError as exc:
        raise RagError(str(exc)) from exc


def list_keyword_lore_documents(vault: Vault, scenario_id: str) -> tuple[list[RagDocument], list[str]]:
    try:
        return _list_keyword_lore_documents(vault, scenario_id)
    except RagDocumentError as exc:
        raise RagError(str(exc)) from exc


def keyword_triggered_lore_results(
    vault: Vault,
    scenario_id: str,
    *,
    user_message: str,
    recent_log: list[dict[str, Any]] | None = None,
    limit: int = KEYWORD_TRIGGER_LIMIT,
    exclude_paths: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        return _keyword_triggered_lore_results(
            vault,
            scenario_id,
            user_message=user_message,
            recent_log=recent_log,
            limit=limit,
            exclude_paths=exclude_paths,
        )
    except RagDocumentError as exc:
        raise RagError(str(exc)) from exc


def keyword_trigger_messages(
    *,
    user_message: str,
    recent_log: list[dict[str, Any]] | None = None,
    limit: int = KEYWORD_TRIGGER_MESSAGE_LIMIT,
) -> list[str]:
    return _keyword_trigger_messages(user_message=user_message, recent_log=recent_log, limit=limit)


def build_rag_query(
    *,
    user_message: str,
    recent_log: list[dict[str, Any]] | None = None,
    state: dict[str, Any] | None = None,
) -> str:
    return _build_rag_query(user_message=user_message, recent_log=recent_log, state=state)


def build_vector_index(
    vault: Vault,
    scenario_id: str,
    config: EmbeddingConfig | None = None,
) -> dict[str, Any]:
    try:
        _rag_vectors.embed_texts = embed_texts
        return _build_vector_index(vault, scenario_id, config)
    except RagVectorError as exc:
        raise RagError(str(exc)) from exc


def read_vector_index(vault: Vault, scenario_id: str) -> dict[str, Any] | None:
    try:
        return _read_vector_index(vault, scenario_id)
    except RagVectorError as exc:
        raise RagError(str(exc)) from exc


def vector_index_rebuild_needed(
    vault: Vault,
    scenario_id: str,
    config: EmbeddingConfig,
    index: dict[str, Any] | None = None,
) -> bool:
    try:
        return _vector_index_rebuild_needed(vault, scenario_id, config, index)
    except RagVectorError as exc:
        raise RagError(str(exc)) from exc


def rebuild_rag_index(vault: Vault, scenario_id: str) -> dict[str, Any]:
    try:
        return _rebuild_rag_index(vault, scenario_id)
    except RagIndexError as exc:
        raise RagError(str(exc)) from exc


def read_rag_index(vault: Vault, scenario_id: str) -> dict[str, Any] | None:
    try:
        return _read_rag_index(vault, scenario_id)
    except RagIndexError as exc:
        raise RagError(str(exc)) from exc


def rag_index_rebuild_needed(vault: Vault, scenario_id: str, index: dict[str, Any] | None = None) -> bool:
    try:
        return _rag_index_rebuild_needed(vault, scenario_id, index)
    except RagIndexError as exc:
        raise RagError(str(exc)) from exc


def clear_rag_stale_marker(vault: Vault, scenario_id: str) -> bool:
    try:
        return _clear_rag_stale_marker(vault, scenario_id)
    except RagIndexError as exc:
        raise RagError(str(exc)) from exc


def query_terms(query: str) -> list[str]:
    return _retrieve_query_terms(query)


def _embedding_text(document: RagDocument) -> str:
    return _retrieve_embedding_text(document)


def _try_vector_similarities(
    vault: Vault,
    scenario_id: str,
    query: str,
    documents: list[RagDocument],
    config: EmbeddingConfig | None,
) -> dict[str, float] | None:
    _rag_retrieve.embed_texts = embed_texts
    return _retrieve_try_vector_similarities(vault, scenario_id, query, documents, config)


def _score_documents_hybrid(
    documents: list[RagDocument],
    terms: list[str],
    vector_sims: dict[str, float],
) -> list[dict[str, Any]]:
    return _retrieve_score_documents_hybrid(documents, terms, vector_sims)

from __future__ import annotations

import json
import re
from datetime import date, datetime
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
JAPANESE_STOP_TERMS = frozenset(
    {
        # 代名詞・指示詞
        "あなた", "これ", "それ", "あれ", "この", "その", "あの", "どの",
        # 助動詞・活用語尾
        "って", "ってい", "してい", "のは", "には", "では",
        "された", "だった", "している", "していた",
        "という", "といった", "ような",
        # 丁寧語
        "です", "ます", "します", "でした", "ました",
        # 汎用動詞（原形）
        "する", "ある", "いる", "なる",
        # 汎用動詞（自然文頻出形）
        "言う", "見る", "思う", "感じる",
    }
)

_MEMORY_RECENCY_MAX_BONUS = 20
_MEMORY_RECENCY_WINDOW_DAYS = 30
_MEMORY_INACTIVE_STATUSES = frozenset({"resolved", "superseded", "archived"})
_MEMORY_STALE_SCORE_PENALTY = -20
_MEMORY_LAST_SEEN_MAX_BONUS = 15
_MEMORY_LAST_SEEN_WINDOW_TURNS = 24


def _validate_type_limits(limits: dict[str, int] | None) -> None:
    """Validate optional per-type count limits for the RAG node.

    Backward compatible: ``None`` is valid and means "no per-type override".
    """
    if limits is None:
        return
    if not isinstance(limits, dict):
        raise RagRetrieveError("RAG limits must be an object mapping type to a non-negative integer")
    for key, value in limits.items():
        if not isinstance(key, str) or not key.strip():
            raise RagRetrieveError("RAG limits keys must be non-empty strings")
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise RagRetrieveError("RAG limits values must be non-negative integers")


def _select_with_type_limits(
    results: list[dict[str, Any]],
    *,
    limits: dict[str, int],
    fallback_limit: int,
) -> list[dict[str, Any]]:
    """Apply a per-type count cap to score-sorted results.

    - cap only (no floor / no reservation): keep a result while its type's running
      count is below the cap.
    - score-gated: callers pass only score>0 results, so unmatched types stay empty.
    - types absent from ``limits`` fall back to ``fallback_limit`` (the shared limit).
    """
    counts: dict[str, int] = {}
    selected: list[dict[str, Any]] = []
    for result in results:
        result_type = result_budget_type(result)
        cap = limits.get(result_type, fallback_limit)
        if counts.get(result_type, 0) < cap:
            selected.append(result)
            counts[result_type] = counts.get(result_type, 0) + 1
    return selected


def retrieve_context(
    vault: Vault,
    *,
    scenario_id: str,
    query: str,
    limit: int = 6,
    sources: list[str] | tuple[str, ...] | None = None,
    embedding_config: EmbeddingConfig | None = None,
    exclude_paths: set[str] | None = None,
    character_match_mode: str = "exact",
    limits: dict[str, int] | None = None,
    allowed_session_ids: set[str] | None = None,
    current_turn: int | None = None,
) -> list[dict[str, Any]]:
    """Retrieve relevant documents using keyword search, optionally blended with vector search."""
    if not is_locus_id(scenario_id):
        raise RagRetrieveError(f"Invalid scenario id: {scenario_id}")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise RagRetrieveError("RAG limit must be a non-negative integer")
    _validate_type_limits(limits)
    if not limits and limit == 0:
        return []

    terms = query_terms(query)
    exact_query = query if isinstance(query, str) else ""
    allowed_sources = set(sources or ["memory", "lore", "characters"])
    documents = _fresh_index_documents(vault, scenario_id, sources=allowed_sources)
    if documents is None:
        documents = _list_documents(vault, scenario_id, sources=allowed_sources)

    if exclude_paths:
        documents = [doc for doc in documents if doc.source_path not in exclude_paths]
    if allowed_session_ids is not None:
        documents = _filter_memory_documents_by_session(documents, allowed_session_ids)
    documents = _filter_searchable_memory_documents(documents)

    if not terms and not documents:
        return []

    vector_sims = try_vector_similarities(vault, scenario_id, query, documents, embedding_config)

    if vector_sims is not None:
        scored = score_documents_hybrid(
            documents,
            terms,
            vector_sims,
            character_match_mode=character_match_mode,
            exact_query=exact_query,
            current_turn=current_turn,
        )
    else:
        if not terms:
            return []
        scored = [
            _score_document(
                document,
                terms,
                character_match_mode=character_match_mode,
                exact_query=exact_query,
                current_turn=current_turn,
            )
            for document in documents
        ]

    results = [result for result in scored if result["score"] > 0]
    results.sort(key=lambda item: (-item["score"], item["source_path"], str(item.get("chunk_id") or "")))
    if limits:
        return _select_with_type_limits(results, limits=limits, fallback_limit=limit)
    return results[:limit]


def _filter_memory_documents_by_session(
    documents: list[RagDocument],
    allowed_session_ids: set[str],
) -> list[RagDocument]:
    filtered: list[RagDocument] = []
    for document in documents:
        if _source_folder(document.source_path) != "memory":
            filtered.append(document)
            continue
        session_id = document.metadata.get("session_id")
        if not isinstance(session_id, str) or not session_id.strip():
            filtered.append(document)
            continue
        if session_id in allowed_session_ids:
            filtered.append(document)
    return filtered


def _filter_searchable_memory_documents(documents: list[RagDocument]) -> list[RagDocument]:
    return [
        document
        for document in documents
        if _source_folder(document.source_path) != "memory"
        or _memory_status(document.metadata) not in _MEMORY_INACTIVE_STATUSES
    ]


def query_terms(query: str) -> list[str]:
    if not isinstance(query, str):
        return []
    raw_terms: list[str] = []
    for match in re.findall(r"[A-Za-z0-9_]{2,}|[ぁ-んァ-ヶ一-龠ー]{2,}", query.lower()):
        raw_terms.append(match)
        if re.fullmatch(r"[ぁ-んァ-ヶ一-龠ー]+", match):
            units = _japanese_term_units(match)
            raw_terms.extend(units)
            for unit in units:
                raw_terms.extend(_japanese_ngrams(unit))
    seen: set[str] = set()
    terms: list[str] = []
    for term in raw_terms:
        if _is_japanese_stop_term(term):
            continue
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
    *,
    character_match_mode: str = "exact",
    exact_query: str = "",
    current_turn: int | None = None,
) -> list[dict[str, Any]]:
    """Score documents using both keyword matching and vector similarity."""
    results: list[dict[str, Any]] = []
    for document in documents:
        keyword_result = _score_document(
            document,
            terms,
            character_match_mode=character_match_mode,
            exact_query=exact_query,
            current_turn=current_turn,
        )
        keyword_score = keyword_result["score"]
        v_sim = vector_sims.get(document_key(document), 0.0)
        is_exact_character = _is_character_document(document) and character_match_mode != "fuzzy"

        if keyword_score > 0:
            boost = max(0.0, v_sim) * keyword_score * 0.4
            combined = keyword_score + boost
        elif is_exact_character:
            combined = 0.0
        elif v_sim >= VECTOR_MATCH_THRESHOLD:
            combined = (v_sim - VECTOR_MATCH_THRESHOLD) / (1.0 - VECTOR_MATCH_THRESHOLD) * VECTOR_ONLY_MAX_SCORE
            keyword_result = {**keyword_result, "content": _excerpt(document.body, []), "matched_terms": []}
            if _source_folder(document.source_path) == "memory":
                combined += _memory_metadata_score_adjustment(document.metadata)
                combined += _memory_last_seen_score(document.metadata, current_turn)
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
    if _is_hiragana_only(value):
        return []
    terms: list[str] = []
    upper = min(6, len(value))
    for size in range(3, upper + 1):
        for index in range(0, len(value) - size + 1):
            term = value[index : index + size]
            if not _is_hiragana_only(term):
                terms.append(term)
    return terms


def _japanese_term_units(value: str) -> list[str]:
    units: list[str] = []
    for term in _japanese_script_terms(value):
        parts = [part for part in re.split(r"[のをにへでとがはもやか、。・]+", term) if len(part) >= 2]
        if parts and parts != [term]:
            units.extend(parts)
        else:
            units.append(term)
    units = [unit for unit in units if _is_japanese_unit_term(unit)]
    seen: set[str] = set()
    deduped: list[str] = []
    for unit in units:
        if unit not in seen:
            seen.add(unit)
            deduped.append(unit)
    return deduped


def _japanese_script_terms(value: str) -> list[str]:
    terms: list[str] = []
    current = ""
    current_kind = ""
    for char in value:
        kind = _japanese_script_kind(char)
        if kind and kind == current_kind:
            current += char
            continue
        if len(current) >= 2:
            terms.append(current)
        current = char if kind else ""
        current_kind = kind
    if len(current) >= 2:
        terms.append(current)
    return terms


def _japanese_script_kind(char: str) -> str:
    if re.fullmatch(r"[ぁ-ん]", char):
        return "hiragana"
    if re.fullmatch(r"[ァ-ヶー]", char):
        return "katakana"
    if re.fullmatch(r"[一-龠]", char):
        return "kanji"
    return ""


def _is_japanese_unit_term(value: str) -> bool:
    return not (_is_hiragana_only(value) and len(value) <= 4)


def _is_hiragana_only(value: str) -> bool:
    return bool(value) and re.fullmatch(r"[ぁ-ん]+", value) is not None


def _is_japanese_stop_term(value: str) -> bool:
    return value in JAPANESE_STOP_TERMS


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
        if item.get("metadata", {}).get("keywords_enabled") is True:
            continue  # handled exclusively by keyword trigger pipeline
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


def _score_document(
    document: RagDocument,
    terms: list[str],
    *,
    character_match_mode: str = "exact",
    exact_query: str = "",
    current_turn: int | None = None,
) -> dict[str, Any]:
    is_character = _is_character_document(document)
    if is_character and character_match_mode != "fuzzy":
        matched_terms = _character_exact_matched_terms(document, terms, exact_query)
    else:
        searchable = _searchable_text(document).lower()
        matched_terms = [term for term in terms if term in searchable]
    if not matched_terms or (not is_character and not _has_significant_match(document, matched_terms)):
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
    source_folder = _source_folder(document.source_path)
    if source_folder == "memory":
        score += _memory_recency_score(document.metadata)
        score += _memory_metadata_score_adjustment(document.metadata)
        score += _memory_last_seen_score(document.metadata, current_turn)
    content = document.body.strip() if is_character else _excerpt(document.body, matched_terms)
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


def _is_character_document(document: RagDocument) -> bool:
    return result_budget_type({"type": document.type, "source_path": document.source_path}) == "character"


def _searchable_text(document: RagDocument) -> str:
    metadata_text = json.dumps(document.metadata, ensure_ascii=False, sort_keys=True)
    if result_budget_type({"type": document.type, "source_path": document.source_path}) == "character":
        return "\n".join(part for part in (document.title, metadata_text) if part)
    return "\n".join(part for part in (document.body, document.title, metadata_text) if part)


def _character_exact_matched_terms(document: RagDocument, terms: list[str], query: str) -> list[str]:
    raw_values = _character_exact_raw_values(document)
    values = _character_exact_values(raw_values)
    matched = [term for term in terms if term in values]
    normalized_query = _normalize_exact_value(query)
    for value in raw_values:
        if not _should_match_normalized_phrase(value):
            continue
        normalized = _normalize_exact_value(value)
        if normalized and normalized in normalized_query and normalized not in matched:
            matched.append(normalized)
    return matched


def _character_exact_raw_values(document: RagDocument) -> list[str]:
    values: list[str] = []
    for value in (
        document.title,
        document.metadata.get("id"),
        document.metadata.get("name"),
    ):
        if isinstance(value, str) and value.strip():
            values.append(value)
    for field in ("aliases", "keywords"):
        raw = document.metadata.get(field)
        items = raw if isinstance(raw, list) else [raw]
        for item in items:
            if isinstance(item, str) and item.strip():
                values.append(item)
    return values


def _character_exact_values(raw_values: list[str]) -> set[str]:
    values: set[str] = set()
    for value in raw_values:
        _add_character_exact_value(values, value)
    return values


def _should_match_normalized_phrase(value: str) -> bool:
    return bool(re.search(r"[\s・･'’`\\-]", value.strip()))


def _add_character_exact_value(values: set[str], value: str) -> None:
    stripped = value.strip().lower()
    values.add(stripped)
    normalized = _normalize_exact_value(stripped)
    if normalized:
        values.add(normalized)


def _normalize_exact_value(value: str) -> str:
    return re.sub(r"[\s・･'’`\\-]+", "", value.strip().lower())


def _metadata_match_score(metadata: dict[str, Any], matched_terms: list[str]) -> int:
    score = 0
    for field in ("tags", "characters", "locations", "topics"):
        value = metadata.get(field)
        values = value if isinstance(value, list) else [value]
        haystack = " ".join(str(item).lower() for item in values if item is not None)
        score += sum(5 for term in matched_terms if term in haystack)
    # keywords: アイテム単位の完全一致で +10（n-gram 部分一致による誤爆を防ぐ）
    kw_value = metadata.get("keywords")
    kw_values = kw_value if isinstance(kw_value, list) else [kw_value]
    terms_set = set(matched_terms)
    matched_kw_count = sum(
        1 for kw in kw_values
        if kw is not None and str(kw).strip().lower() in terms_set
    )
    score += matched_kw_count * 10
    # locus-rag のキーワードにマッチした場合の追加ボーナス（作者の意図による検索シグナルを尊重）
    if metadata.get("chunk_type") == "locus-rag" and matched_kw_count > 0:
        score += 10
    return score


def _memory_recency_score(metadata: dict[str, Any]) -> int:
    raw = metadata.get("created")
    if not raw:
        return 0
    try:
        if isinstance(raw, str):
            created_date = datetime.fromisoformat(raw).date()
        elif isinstance(raw, datetime):
            created_date = raw.date()
        elif isinstance(raw, date):
            created_date = raw
        else:
            return 0
    except (ValueError, TypeError):
        return 0
    age_days = (date.today() - created_date).days
    if age_days < 0:
        return 0
    return max(0, _MEMORY_RECENCY_MAX_BONUS - age_days)


def _memory_metadata_score_adjustment(metadata: dict[str, Any]) -> int:
    score = _memory_importance_score(metadata)
    if _memory_status(metadata) == "stale":
        score += _MEMORY_STALE_SCORE_PENALTY
    return score


def _memory_last_seen_score(metadata: dict[str, Any], current_turn: int | None) -> int:
    if not isinstance(current_turn, int) or isinstance(current_turn, bool) or current_turn < 0:
        return 0
    value = metadata.get("last_seen_turn")
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > current_turn:
        return 0
    distance = current_turn - value
    if distance > _MEMORY_LAST_SEEN_WINDOW_TURNS:
        return 0
    return max(0, _MEMORY_LAST_SEEN_MAX_BONUS - distance)


def _memory_importance_score(metadata: dict[str, Any]) -> int:
    value = metadata.get("importance")
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, min(100, int(value)))
    return 0


def _memory_status(metadata: dict[str, Any]) -> str:
    value = metadata.get("status")
    if not isinstance(value, str) or not value.strip():
        return "active"
    return value.strip().lower()


def _has_significant_match(document: RagDocument, matched_terms: list[str]) -> bool:
    return any(
        _is_significant_term(term)
        or _term_matches_title(document.title, term)
        or _term_matches_metadata(document.metadata, term)
        for term in matched_terms
    )


def _is_significant_term(term: str) -> bool:
    return re.search(r"[A-Za-z0-9_ァ-ヶ一-龠]", term) is not None


def _term_matches_title(title: str, term: str) -> bool:
    return bool(title and term and term in title.lower())


def _term_matches_metadata(metadata: dict[str, Any], term: str) -> bool:
    for field in ("keywords", "tags", "characters", "locations", "topics"):
        value = metadata.get(field)
        values = value if isinstance(value, list) else [value]
        haystack = " ".join(str(item).lower() for item in values if item is not None)
        if term in haystack:
            return True
    return False


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

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from app.api_validation import ApiBadRequest
from app.loaders import load_scenario
from app.embedding import EmbeddingError, get_embedding_config
from app.rag import (
    build_vector_index,
    rag_index_rebuild_needed,
    read_rag_index,
    read_vector_index,
    rebuild_rag_index,
    vector_index_rebuild_needed,
)
from app.vault import Vault, VaultError, VaultFileError
from app.api.common import _atomic_write_text, _markdown_with_frontmatter, _timeline_excerpt, _utc_timestamp


_ALLOWED_MEMORY_KINDS: frozenset[str] = frozenset({"session_summaries", "extracted_facts", "unresolved_threads"})


_ALLOWED_MEMORY_STATUSES: frozenset[str] = frozenset({"active", "resolved", "superseded", "stale", "archived"})


def _update_memory_metadata_response(
    vault: Vault,
    scenario_id: str,
    kind: str,
    memory_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if kind not in _ALLOWED_MEMORY_KINDS:
        raise ApiBadRequest(f"Unknown memory kind: {kind!r}")
    if not re.match(r'^[A-Za-z0-9_-]+$', memory_id):
        raise ApiBadRequest(f"Invalid memory_id: {memory_id!r}")
    load_scenario(vault, scenario_id)
    scenario_relative = f"memory/{kind}/{memory_id}.md"
    vault_relative = f"rp/scenarios/{scenario_id}/{scenario_relative}"
    path = vault.resolve(vault_relative)
    if not path.is_file():
        raise ApiBadRequest(f"Memory not found: {kind}/{memory_id}")

    try:
        document = vault.load_markdown(vault_relative)
    except VaultFileError as exc:
        raise ApiBadRequest(f"memory markdown is unreadable: {scenario_relative}") from exc

    metadata = dict(document.frontmatter)
    changed = False
    if "rag_enabled" in payload:
        rag_enabled = payload.get("rag_enabled")
        if not isinstance(rag_enabled, bool):
            raise ApiBadRequest("rag_enabled must be a boolean")
        if rag_enabled:
            if metadata.pop("rag", None) is not None:
                changed = True
        elif metadata.get("rag") is not False:
            metadata["rag"] = False
            changed = True
    if "status" in payload:
        status = payload.get("status")
        if not isinstance(status, str) or status not in _ALLOWED_MEMORY_STATUSES:
            raise ApiBadRequest(f"Invalid memory status: {status!r}")
        if metadata.get("status") != status:
            metadata["status"] = status
            if status == "resolved" and not metadata.get("resolved_at"):
                metadata["resolved_at"] = _utc_timestamp()
            changed = True

    if changed:
        _atomic_write_text(path, _markdown_with_frontmatter(metadata, document.body))
        from app.memory_summarizer import mark_rag_index_stale
        mark_rag_index_stale(vault, scenario_id, [scenario_relative])

    normalized = _normalize_memory_metadata(metadata)
    return {
        "scenario_id": scenario_id,
        "kind": kind,
        "memory_id": memory_id,
        "path": scenario_relative,
        "metadata": normalized,
        "rag_enabled": normalized.get("rag") is not False,
        "status": normalized["status"],
        "saved": changed,
    }


def _scenario_rag_status(vault: Vault, scenario_id: str) -> dict[str, Any]:
    load_scenario(vault, scenario_id)
    memory_counts = _memory_file_counts(vault, scenario_id)
    index = read_rag_index(vault, scenario_id)
    rebuild_needed = rag_index_rebuild_needed(vault, scenario_id, index)
    stale_path = vault.resolve("rp/_cache/rag/stale.json")
    stale_payload: dict[str, Any] | None = None
    stale_error = ""
    if stale_path.is_file():
        try:
            loaded = vault.load_json("rp/_cache/rag/stale.json")
            if isinstance(loaded, dict):
                stale_payload = loaded
            else:
                stale_error = "stale marker root is not an object"
        except VaultError as exc:
            stale_error = str(exc)

    marker_scenario_id = stale_payload.get("scenario_id") if stale_payload else None
    stale_for_scenario = marker_scenario_id == scenario_id
    return {
        "scenario_id": scenario_id,
        "rag_index": {
            "implemented": True,
            "indexed": index is not None,
            "version": index.get("version") if index else None,
            "document_count": index.get("document_count") if index else 0,
            "indexed_at": index.get("indexed_at") if index else "",
            "rebuild_needed": rebuild_needed,
            "stale": stale_for_scenario or bool(stale_error) or rebuild_needed,
            "stale_marker_exists": stale_path.is_file(),
            "stale_marker_scenario_id": marker_scenario_id,
            "reason": stale_payload.get("reason") if stale_payload else "",
            "marked_at": stale_payload.get("marked_at") if stale_payload else "",
            "created_files": stale_payload.get("created_files", []) if stale_for_scenario else [],
            "error": stale_error,
        },
        "memory": {
            "counts": memory_counts,
            "total": sum(memory_counts.values()),
        },
    }


def _scenario_rag_rebuild_response(vault: Vault, scenario_id: str) -> dict[str, Any]:
    load_scenario(vault, scenario_id)
    index = rebuild_rag_index(vault, scenario_id)
    return {
        "scenario_id": scenario_id,
        "rebuilt": True,
        "index": {
            "version": index["version"],
            "document_count": index["document_count"],
            "indexed_at": index["indexed_at"],
            "incremental": index.get("incremental", {}),
        },
    }


def _scenario_memory_response(vault: Vault, scenario_id: str, *, session_id: str | None = None) -> dict[str, Any]:
    load_scenario(vault, scenario_id)
    base = vault.resolve(f"rp/scenarios/{scenario_id}")
    memory_root = base / "memory"
    kinds = ("session_summaries", "extracted_facts", "unresolved_threads")
    groups: dict[str, list[dict[str, Any]]] = {kind: [] for kind in kinds}
    index = read_rag_index(vault, scenario_id)
    indexed_paths = _rag_index_source_paths(index)
    stale_created_paths = set(_scenario_rag_status(vault, scenario_id)["rag_index"].get("created_files", []))

    for kind in kinds:
        directory = memory_root / kind
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            if not path.is_file():
                continue
            scenario_relative = path.relative_to(base).as_posix()
            try:
                document = vault.load_markdown(f"rp/scenarios/{scenario_id}/{scenario_relative}")
            except VaultFileError as exc:
                raise ApiBadRequest(f"memory markdown is unreadable: {scenario_relative}") from exc
            metadata = dict(document.frontmatter)
            if session_id is not None and metadata.get("session_id") != session_id:
                continue
            body = document.body.strip()
            stat = path.stat()
            normalized_metadata = _normalize_memory_metadata(metadata)
            groups[kind].append(
                {
                    "path": scenario_relative,
                    "kind": kind,
                    "memory_kind": normalized_metadata.get("memory_kind") or _memory_kind_from_folder(kind),
                    "title": _memory_title(path, normalized_metadata),
                    "metadata": normalized_metadata,
                    "content": body,
                    "excerpt": _timeline_excerpt(body, limit=120),
                    "updated_at": stat.st_mtime,
                    "rag_enabled": normalized_metadata.get("rag") is not False,
                    "in_index": scenario_relative in indexed_paths,
                    "stale_created": scenario_relative in stale_created_paths,
                    "status": normalized_metadata["status"],
                    "source": normalized_metadata["source"],
                    "confidence": normalized_metadata["confidence"],
                    "last_seen_turn": normalized_metadata.get("last_seen_turn"),
                    "characters": normalized_metadata.get("characters", []),
                    "locations": normalized_metadata.get("locations", []),
                    "topics": normalized_metadata.get("topics", []),
                }
            )

    for items in groups.values():
        items.sort(key=lambda item: (-item["updated_at"], item["path"]))

    return {
        "scenario_id": scenario_id,
        **({"session_id": session_id} if session_id is not None else {}),
        "groups": groups,
        "counts": {kind: len(items) for kind, items in groups.items()},
        "total": sum(len(items) for items in groups.values()),
    }


def _normalize_memory_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(metadata)
    status = normalized.get("status")
    if not isinstance(status, str) or not status.strip():
        normalized["status"] = "active"
    source = normalized.get("source")
    if not isinstance(source, str) or not source.strip():
        normalized["source"] = "unknown"
    confidence = normalized.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
        normalized["confidence"] = None
    for field in ("supersedes", "superseded_by", "characters", "locations", "topics"):
        value = normalized.get(field)
        if not isinstance(value, list):
            normalized[field] = []
        else:
            normalized[field] = [item for item in value if isinstance(item, str)]
    return normalized


def _rag_index_source_paths(index: dict[str, Any] | None) -> set[str]:
    documents = index.get("documents") if isinstance(index, dict) else []
    if not isinstance(documents, list):
        return set()
    return {item["source_path"] for item in documents if isinstance(item, dict) and isinstance(item.get("source_path"), str)}


def _memory_kind_from_folder(folder: str) -> str:
    return {
        "session_summaries": "session_summary",
        "extracted_facts": "fact",
        "unresolved_threads": "unresolved_thread",
    }.get(folder, "memory")


def _scenario_rag_vector_status(vault: Vault, scenario_id: str) -> dict[str, Any]:
    load_scenario(vault, scenario_id)
    config = get_embedding_config()
    index = read_vector_index(vault, scenario_id)
    rebuild_needed = vector_index_rebuild_needed(vault, scenario_id, config, index) if config.enabled else False
    return {
        "scenario_id": scenario_id,
        "embedding": config.as_safe_dict(),
        "vector_index": {
            "indexed": index is not None,
            "version": index.get("version") if index else None,
            "model": index.get("model") if index else None,
            "document_count": index.get("document_count") if index else 0,
            "indexed_at": index.get("indexed_at") if index else "",
            "rebuild_needed": rebuild_needed,
        },
    }


def _scenario_rag_rebuild_vectors_response(vault: Vault, scenario_id: str) -> dict[str, Any]:
    load_scenario(vault, scenario_id)
    config = get_embedding_config()
    if not config.enabled:
        raise ApiBadRequest("Embedding is not configured (set LOCUS_EMBEDDING_MODEL and endpoint env vars)")
    try:
        index = build_vector_index(vault, scenario_id, config)
    except EmbeddingError as exc:
        raise ApiBadRequest(str(exc)) from exc
    return {
        "scenario_id": scenario_id,
        "rebuilt": True,
        "index": {
            "version": index["version"],
            "model": index["model"],
            "document_count": index["document_count"],
            "indexed_at": index["indexed_at"],
        },
    }


def _memory_title(path: Path, metadata: dict[str, Any]) -> str:
    for key in ("title", "name", "id"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return path.stem


def _memory_file_counts(vault: Vault, scenario_id: str) -> dict[str, int]:
    base = vault.resolve(f"rp/scenarios/{scenario_id}/memory")
    counts = {"session_summaries": 0, "extracted_facts": 0, "unresolved_threads": 0}
    if not base.exists():
        return counts
    for folder in counts:
        directory = base / folder
        if directory.is_dir():
            counts[folder] = len([path for path in directory.glob("*.md") if path.is_file()])
    return counts

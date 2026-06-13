from __future__ import annotations

from typing import Any

from app.token_usage import estimate_text_tokens


DEFAULT_RAG_TOKEN_BUDGET = 6000
DEFAULT_RAG_TYPE_TOKEN_BUDGETS = {
    "memory": 2400,
    "lore": 2400,
    "character": 1800,
}


def budget_rag_results(
    results: list[dict[str, Any]],
    *,
    token_budget: int | None = DEFAULT_RAG_TOKEN_BUDGET,
    token_budgets: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    if not results:
        return []
    total_budget = _normalize_budget(token_budget)
    if total_budget == 0:
        return []
    type_budgets = {**DEFAULT_RAG_TYPE_TOKEN_BUDGETS, **(token_budgets or {})}
    type_budgets = {key: value for key, value in type_budgets.items() if _normalize_budget(value) is not None}

    selected: list[dict[str, Any]] = []
    used_total = 0
    used_by_type: dict[str, int] = {}
    for result in results:
        result_type = result_budget_type(result)
        total_remaining = None if total_budget is None else max(0, total_budget - used_total)
        type_budget = _normalize_budget(type_budgets.get(result_type))
        type_used = used_by_type.get(result_type, 0)
        type_remaining = None if type_budget is None else max(0, type_budget - type_used)
        available = _minimum_budget(total_remaining, type_remaining)
        if available == 0:
            continue
        fitted = _fit_result_to_budget(result, available)
        if fitted is None:
            continue
        fitted_result, estimated_tokens = fitted
        selected.append({**fitted_result, "estimated_tokens": estimated_tokens})
        used_total += estimated_tokens
        used_by_type[result_type] = type_used + estimated_tokens
    return selected


def format_rag_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return ""
    grouped: dict[str, list[dict[str, Any]]] = {"memory": [], "lore": [], "character": [], "other": []}
    for result in results:
        grouped.setdefault(result_budget_type(result), grouped["other"]).append(result)
    sections = []
    for section_type, title in (
        ("memory", "Relevant Memory"),
        ("lore", "Relevant Lore"),
        ("character", "Relevant Characters"),
        ("other", "Other Relevant Context"),
    ):
        items = grouped.get(section_type) or []
        if not items:
            continue
        blocks = [_format_result_block(result) for result in items]
        sections.append(f"### {title}\n" + "\n\n".join(blocks))
    return "\n\n".join(sections)


def result_budget_type(result: dict[str, Any]) -> str:
    value = str(result.get("type") or "").strip().lower()
    if value in {"memory", "session_summary", "extracted_fact", "unresolved_thread"}:
        return "memory"
    if value == "lore":
        return "lore"
    if value in {"character", "characters"}:
        return "character"
    source_path = str(result.get("source_path") or "")
    if source_path.startswith("memory/"):
        return "memory"
    if source_path.startswith("lore/"):
        return "lore"
    if source_path.startswith("characters/"):
        return "character"
    return "other"


def _format_result_block(result: dict[str, Any]) -> str:
    title = result["title"] or result["source_path"]
    header_lines = [f"#### {title}", f"source: {result['source_path']}"]
    chunk_id = result.get("chunk_id")
    if isinstance(chunk_id, str) and chunk_id:
        header_lines.append(f"chunk: {chunk_id}")
    heading_path = result.get("heading_path")
    if isinstance(heading_path, list) and all(isinstance(item, str) for item in heading_path) and heading_path:
        header_lines.append(f"heading: {' > '.join(heading_path)}")
    header_lines.extend([f"type: {result['type']}", f"score: {result['score']}"])
    header_lines.extend(_memory_metadata_lines(result))
    header = "\n".join(header_lines)
    content = str(result.get("content", "")).strip()
    return f"{header}\n{content}" if content else header


def _memory_metadata_lines(result: dict[str, Any]) -> list[str]:
    if result_budget_type(result) != "memory":
        return []
    metadata = result.get("metadata")
    if not isinstance(metadata, dict):
        return []
    lines: list[str] = []
    for key in ("memory_kind", "session_id", "turn_range", "importance"):
        value = metadata.get(key)
        if isinstance(value, (str, int, float)) and not isinstance(value, bool) and str(value).strip():
            lines.append(f"{key}: {value}")
    return lines


def _fit_result_to_budget(result: dict[str, Any], available_tokens: int | None) -> tuple[dict[str, Any], int] | None:
    block = _format_result_block(result)
    block_tokens = estimate_text_tokens(block)
    if available_tokens is None or block_tokens <= available_tokens:
        return result, block_tokens
    if result_budget_type(result) == "character":
        return None

    header_result = {**result, "content": ""}
    header_tokens = estimate_text_tokens(_format_result_block(header_result))
    if header_tokens >= available_tokens:
        return None

    content = str(result.get("content", "")).strip()
    if not content:
        return None
    low = 0
    high = len(content)
    best = ""
    while low <= high:
        middle = (low + high) // 2
        candidate = content[:middle].rstrip()
        if middle < len(content):
            candidate = f"{candidate}..."
        candidate_result = {**result, "content": candidate}
        candidate_tokens = estimate_text_tokens(_format_result_block(candidate_result))
        if candidate_tokens <= available_tokens:
            best = candidate
            low = middle + 1
        else:
            high = middle - 1
    if not best:
        return None
    fitted_result = {**result, "content": best}
    return fitted_result, estimate_text_tokens(_format_result_block(fitted_result))


def _normalize_budget(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return max(0, int(value))
    return None


def _minimum_budget(*values: int | None) -> int | None:
    numeric = [value for value in values if value is not None]
    return min(numeric) if numeric else None

/**
 * @param {Record<string, Array<Record<string, any>>>} groups
 */
export function buildMemoryFilterOptions(groups) {
  const kinds = new Set();
  const statuses = new Set();
  const sources = new Set();
  for (const [kind, items] of Object.entries(groups || {})) {
    kinds.add(kind);
    for (const item of items || []) {
      if (item.status) statuses.add(String(item.status));
      if (item.source) sources.add(String(item.source));
    }
  }
  return {
    kinds: Array.from(kinds).sort(),
    statuses: Array.from(statuses).sort(),
    sources: Array.from(sources).sort()
  };
}

/**
 * @param {string} kind
 * @param {Record<string, any>} item
 * @param {Record<string, string>} filters
 */
export function memoryMatchesFilters(kind, item, filters) {
  if (filters.kind !== "all" && kind !== filters.kind) return false;
  if (filters.status !== "all" && item.status !== filters.status) return false;
  if (filters.source !== "all" && item.source !== filters.source) return false;
  if (filters.rag === "enabled" && item.rag_enabled !== true) return false;
  if (filters.rag === "disabled" && item.rag_enabled !== false) return false;
  if (!memoryFieldMatches(item.characters, filters.character || "")) return false;
  if (!memoryFieldMatches(item.locations, filters.location || "")) return false;
  if (!memoryFieldMatches(item.topics, filters.topic || "")) return false;
  return true;
}

/**
 * @param {unknown} value
 * @param {string} filter
 */
export function memoryFieldMatches(value, filter) {
  const needle = filter.trim().toLowerCase();
  if (!needle) return true;
  const values = Array.isArray(value) ? value : [value];
  return values.some((item) => String(item || "").toLowerCase().includes(needle));
}

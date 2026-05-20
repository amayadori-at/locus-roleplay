export const DEFAULT_GROUP_SIZE = 10;
export const VIRTUAL_THRESHOLD = 200;
export const ESTIMATED_ROW_HEIGHT = 96;
export const OVERSCAN_ROWS = 8;

/** @param {Array<Record<string, any>> | undefined} branches */
export function normalizedBranches(branches) {
  return Array.isArray(branches) ? branches : [];
}

/** @param {string | number} value */
export function normalizeGroupSize(value) {
  const parsed = Number.parseInt(String(value), 10);
  if (!Number.isFinite(parsed) || parsed < 1) return DEFAULT_GROUP_SIZE;
  return Math.min(100, parsed);
}

/**
 * @param {Array<Record<string, any>>} source
 * @param {string} query
 * @param {boolean} onlyBookmarked
 */
export function filterTimelineItems(source, query, onlyBookmarked) {
  const normalized = query.trim().toLowerCase();
  const base = onlyBookmarked ? source.filter((item) => item.bookmarked) : source;
  if (!normalized) return base;
  return base.filter((item) => {
    const haystack = [
      item.turn,
      item.role,
      item.excerpt,
      item.timestamp,
      ...normalizedBranches(item.branches).map((branch) => `${branch.display_name || ""} ${branch.session_id || ""}`)
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(normalized);
  });
}

/**
 * @param {Array<Record<string, any>>} source
 * @param {number} size
 * @param {Record<string, boolean>} collapsed
 * @returns {Array<Record<string, any>>}
 */
export function buildTimelineRows(source, size, collapsed) {
  if (!size) {
    return source.map((item, index) => ({ type: "item", item, key: `item-${item.turn || index}-${item.role || index}` }));
  }

  /** @type {Array<Record<string, any>>} */
  const rows = [];
  /** @type {Map<string, { key: string, start: number, end: number, items: Array<Record<string, any>> }>} */
  const groups = new Map();
  for (const item of source) {
    const turn = typeof item.turn === "number" ? item.turn : 0;
    const start = Math.floor(Math.max(0, turn - 1) / size) * size + 1;
    const end = start + size - 1;
    const key = `${start}-${end}`;
    if (!groups.has(key)) {
      groups.set(key, { key, start, end, items: [] });
    }
    const group = groups.get(key);
    if (group) group.items.push(item);
  }

  for (const group of groups.values()) {
    const isCollapsed = collapsed[group.key] === true;
    rows.push({ type: "group", key: group.key, start: group.start, end: group.end, count: group.items.length, collapsed: isCollapsed });
    if (!isCollapsed) {
      group.items.forEach((item, index) => {
        rows.push({ type: "item", item, key: `item-${group.key}-${item.turn || index}-${item.role || index}` });
      });
    }
  }
  return rows;
}

/**
 * @param {number} total
 * @param {number} top
 * @param {number} viewportHeight
 * @param {boolean} enabled
 */
export function getVirtualWindow(total, top, viewportHeight, enabled) {
  if (!enabled) return { start: 0, end: total };
  const first = Math.max(0, Math.floor(top / ESTIMATED_ROW_HEIGHT) - OVERSCAN_ROWS);
  const visibleCount = Math.ceil(viewportHeight / ESTIMATED_ROW_HEIGHT) + OVERSCAN_ROWS * 2;
  return { start: first, end: Math.min(total, first + visibleCount) };
}

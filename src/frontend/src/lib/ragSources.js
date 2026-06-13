/**
 * @typedef {Record<string, any>} RagSource
 * @typedef {{ type: string, label: string, items: RagSource[] }} RagSourceGroup
 */

/**
 * @param {RagSource} result
 */
export function ragSourceType(result) {
  const explicitType = String(result?.type || "").trim().toLowerCase();
  if (["memory", "session_summary", "extracted_fact", "fact", "relationship", "unresolved_thread"].includes(explicitType)) {
    return "memory";
  }
  if (explicitType === "lore") {
    return "lore";
  }
  if (["character", "characters"].includes(explicitType)) {
    return "character";
  }
  const sourcePath = String(result?.source_path || "");
  if (sourcePath.startsWith("memory/")) return "memory";
  if (sourcePath.startsWith("lore/")) return "lore";
  if (sourcePath.startsWith("characters/")) return "character";
  return "other";
}

/**
 * @param {string} type
 */
export function ragSourceGroupLabel(type) {
  return {
    memory: "Relevant Memory",
    lore: "Relevant Lore",
    character: "Relevant Characters",
    other: "Other Relevant Context"
  }[type] || "Other Relevant Context";
}

/**
 * @param {Array<Record<string, any>> | undefined | null} results
 * @returns {RagSourceGroup[]}
 */
export function groupedRagSources(results) {
  /** @type {Record<string, RagSource[]>} */
  const groups = {
    memory: [],
    lore: [],
    character: [],
    other: []
  };
  for (const result of Array.isArray(results) ? results : []) {
    groups[ragSourceType(result)].push(result);
  }
  return Object.entries(groups)
    .filter(([, items]) => items.length > 0)
    .map(([type, items]) => ({
      type,
      label: ragSourceGroupLabel(type),
      items
    }));
}

/**
 * @param {unknown} value
 */
export function formatHeadingPath(value) {
  if (!Array.isArray(value)) return "";
  const parts = value.filter((item) => typeof item === "string" && item.trim()).map((item) => item.trim());
  return parts.join(" > ");
}

/**
 * @param {unknown} value
 */
export function formatMatchedTerms(value) {
  if (!Array.isArray(value)) return "";
  return value
    .filter((item) => typeof item === "string" && item.trim())
    .map((item) => item.trim())
    .join(", ");
}

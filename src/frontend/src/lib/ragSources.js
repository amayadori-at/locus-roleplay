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
 * @param {RagSource} result
 * @param {number} index
 */
export function ragSourceKey(result, index) {
  const base = result?.chunk_id || result?.source_path || result?.title || result?.type || "rag";
  return `${String(base)}:${index}`;
}

/**
 * @param {RagSource} result
 */
export function ragSourceContent(result) {
  const content = result?.content;
  return typeof content === "string" ? content : "";
}

/**
 * @param {RagSource} result
 */
export function ragSourceContentLength(result) {
  return ragSourceContent(result).length;
}

/**
 * @param {RagSource} result
 * @param {number} [maxLength]
 */
export function ragSourceContentPreview(result, maxLength = 320) {
  const content = ragSourceContent(result).trim();
  if (!content || content.length <= maxLength) return content;
  return `${content.slice(0, maxLength).trimEnd()}...`;
}

/**
 * @param {RagSource} result
 * @param {number} [maxLength]
 */
export function isRagSourceContentTruncated(result, maxLength = 320) {
  return ragSourceContent(result).trim().length > maxLength;
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

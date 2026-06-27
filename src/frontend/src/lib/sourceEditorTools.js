/**
 * @param {string} content
 * @returns {{ frontmatter: string, body: string, hasFrontmatter: boolean }}
 */
export function splitFrontmatter(content) {
  if (!content.startsWith("---\n")) {
    return { frontmatter: "", body: content, hasFrontmatter: false };
  }
  const end = content.indexOf("\n---", 4);
  if (end === -1) {
    return { frontmatter: "", body: content, hasFrontmatter: false };
  }
  const markerEnd = content.indexOf("\n", end + 4);
  let bodyStart = markerEnd === -1 ? content.length : markerEnd + 1;
  if (content[bodyStart] === "\n") bodyStart += 1;
  return {
    frontmatter: content.slice(4, end),
    body: content.slice(bodyStart),
    hasFrontmatter: true
  };
}

/**
 * @param {string} content
 * @param {Record<string, string | number | boolean | string[]>} fields
 */
export function upsertFrontmatterFields(content, fields) {
  const split = splitFrontmatter(content);
  const lines = split.hasFrontmatter ? split.frontmatter.split("\n") : [];
  const used = new Set();
  const nextLines = [];
  for (const line of lines) {
    const match = /^([A-Za-z0-9_-]+):/.exec(line);
    if (!match || !(match[1] in fields)) {
      nextLines.push(line);
      continue;
    }
    used.add(match[1]);
    nextLines.push(...formatYamlField(match[1], fields[match[1]]));
  }
  for (const [key, value] of Object.entries(fields)) {
    if (!used.has(key)) {
      nextLines.push(...formatYamlField(key, value));
    }
  }
  const frontmatter = `---\n${nextLines.join("\n").replace(/\n+$/, "")}\n---\n\n`;
  return frontmatter + split.body.replace(/^\n+/, "");
}

/**
 * @param {string} key
 * @param {string | number | boolean | string[]} value
 */
export function formatYamlField(key, value) {
  if (Array.isArray(value)) {
    const items = value.map((item) => `  - ${escapeYamlScalar(item)}`);
    return [`${key}:`, ...items];
  }
  return [`${key}: ${typeof value === "string" ? escapeYamlScalar(value) : String(value)}`];
}

/** @param {string} value */
function escapeYamlScalar(value) {
  if (/^[A-Za-z0-9_-]+$/.test(value)) return value;
  return JSON.stringify(value);
}

/**
 * @param {string} content
 * @param {number} start
 * @param {number} end
 * @param {{ keywords?: string, priority?: string | number, title?: string }} attrs
 */
export function insertLocusRagTag(content, start, end, attrs = {}) {
  const safeStart = Math.max(0, Math.min(start, content.length));
  const safeEnd = Math.max(safeStart, Math.min(end, content.length));
  const selected = content.slice(safeStart, safeEnd) || "ここにRAG対象本文を記述します。";
  const attributes = [];
  if (attrs.keywords && String(attrs.keywords).trim()) {
    attributes.push(`keywords=${JSON.stringify(String(attrs.keywords).trim())}`);
  }
  if (attrs.priority !== undefined && attrs.priority !== null && String(attrs.priority).trim() !== "") {
    attributes.push(`priority=${JSON.stringify(String(attrs.priority).trim())}`);
  }
  if (attrs.title && String(attrs.title).trim()) {
    attributes.push(`title=${JSON.stringify(String(attrs.title).trim())}`);
  }
  const open = attributes.length ? `<locus-rag ${attributes.join(" ")}>` : "<locus-rag>";
  const block = `${open}\n${selected.trim()}\n</locus-rag>`;
  return {
    content: `${content.slice(0, safeStart)}${block}${content.slice(safeEnd)}`,
    selectionStart: safeStart + open.length + 1,
    selectionEnd: safeStart + open.length + 1 + selected.trim().length
  };
}

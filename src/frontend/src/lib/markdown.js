/**
 * Small safe Markdown renderer for chat bubbles.
 *
 * This intentionally does not support raw HTML. User / model text is escaped
 * before limited Markdown syntax is converted.
 *
 * @param {string} raw
 */
export function renderMarkdown(raw) {
  const lines = String(raw || "").replace(/\r\n?/g, "\n").split("\n");
  /** @type {string[]} */
  const html = [];
  /** @type {string[]} */
  let paragraph = [];
  let inFence = false;
  /** @type {string[]} */
  let fenceLines = [];

  const flushParagraph = () => {
    if (!paragraph.length) {
      return;
    }
    html.push(`<p>${paragraph.map(renderInline).join("<br>")}</p>`);
    paragraph = [];
  };

  const flushFence = () => {
    html.push(`<pre><code>${escapeHtml(fenceLines.join("\n"))}</code></pre>`);
    fenceLines = [];
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();

    if (trimmed.startsWith("```")) {
      if (inFence) {
        flushFence();
        inFence = false;
      } else {
        flushParagraph();
        inFence = true;
        fenceLines = [];
      }
      continue;
    }

    if (inFence) {
      fenceLines.push(line);
      continue;
    }

    if (!trimmed) {
      flushParagraph();
      continue;
    }

    const table = collectTable(lines, index);
    if (table) {
      flushParagraph();
      html.push(renderTable(table));
      index = table.nextIndex - 1;
      continue;
    }

    const heading = /^(#{1,4})\s+(.+)$/.exec(trimmed);
    if (heading) {
      flushParagraph();
      const level = heading[1].length;
      html.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
      continue;
    }

    if (/^ {0,3}([-*_])(?:\s*\1){2,}\s*$/.test(line)) {
      flushParagraph();
      html.push("<hr>");
      continue;
    }

    if (trimmed.startsWith("> ")) {
      flushParagraph();
      html.push(`<blockquote>${renderInline(trimmed.slice(2))}</blockquote>`);
      continue;
    }

    const unorderedItems = collectList(lines, index, /^[-*]\s+(.+)$/);
    if (unorderedItems.items.length) {
      flushParagraph();
      html.push(`<ul>${unorderedItems.items.map((item) => `<li>${renderInline(item)}</li>`).join("")}</ul>`);
      index = unorderedItems.nextIndex - 1;
      continue;
    }

    const orderedItems = collectList(lines, index, /^\d+[.)]\s+(.+)$/);
    if (orderedItems.items.length) {
      flushParagraph();
      html.push(`<ol>${orderedItems.items.map((item) => `<li>${renderInline(item)}</li>`).join("")}</ol>`);
      index = orderedItems.nextIndex - 1;
      continue;
    }

    paragraph.push(line);
  }

  if (inFence) {
    flushFence();
  }
  flushParagraph();
  return html.join("");
}

/**
 * @typedef {{
 *   headers: string[],
 *   alignments: Array<"left" | "center" | "right" | null>,
 *   rows: string[][],
 *   nextIndex: number,
 * }} MarkdownTable
 */

/**
 * @param {string[]} lines
 * @param {number} start
 * @returns {MarkdownTable | null}
 */
function collectTable(lines, start) {
  if (start + 1 >= lines.length) {
    return null;
  }
  const header = splitTableRow(lines[start]);
  const separator = splitTableRow(lines[start + 1]);
  if (!header || !separator || header.length !== separator.length || !separator.every(isTableSeparatorCell)) {
    return null;
  }

  /** @type {string[][]} */
  const rows = [];
  let index = start + 2;
  while (index < lines.length) {
    if (!lines[index].trim()) {
      break;
    }
    const row = splitTableRow(lines[index]);
    if (!row) {
      break;
    }
    rows.push(normalizeTableRow(row, header.length));
    index += 1;
  }

  return {
    headers: normalizeTableRow(header, header.length),
    alignments: separator.map(tableAlignment),
    rows,
    nextIndex: index,
  };
}

/** @param {MarkdownTable} table */
function renderTable(table) {
  const headers = table.headers
    .map((cell, index) => `<th${alignmentAttribute(table.alignments[index])}>${renderInline(cell)}</th>`)
    .join("");
  const rows = table.rows
    .map((row) => `<tr>${row.map((cell, index) => `<td${alignmentAttribute(table.alignments[index])}>${renderInline(cell)}</td>`).join("")}</tr>`)
    .join("");
  return `<div class="markdown-table-scroll"><table><thead><tr>${headers}</tr></thead><tbody>${rows}</tbody></table></div>`;
}

/** @param {string} line */
function splitTableRow(line) {
  if (!line.includes("|")) {
    return null;
  }
  let value = line.trim();
  if (value.startsWith("|")) {
    value = value.slice(1);
  }
  if (value.endsWith("|")) {
    value = value.slice(0, -1);
  }
  const cells = splitUnescapedPipes(value).map((cell) => cell.replaceAll("\\|", "|").trim());
  return cells.length >= 2 ? cells : null;
}

/** @param {string} value */
function splitUnescapedPipes(value) {
  /** @type {string[]} */
  const cells = [];
  let current = "";
  for (let index = 0; index < value.length; index += 1) {
    const char = value[index];
    if (char === "|" && value[index - 1] !== "\\") {
      cells.push(current);
      current = "";
      continue;
    }
    current += char;
  }
  cells.push(current);
  return cells;
}

/** @param {string[]} row @param {number} cellCount */
function normalizeTableRow(row, cellCount) {
  return Array.from({ length: cellCount }, (_, index) => row[index] || "");
}

/** @param {string} cell */
function isTableSeparatorCell(cell) {
  return /^:?-+:?$/.test(cell.trim());
}

/** @param {string} cell */
function tableAlignment(cell) {
  const trimmed = cell.trim();
  if (trimmed.startsWith(":") && trimmed.endsWith(":")) return "center";
  if (trimmed.endsWith(":")) return "right";
  if (trimmed.startsWith(":")) return "left";
  return null;
}

/** @param {"left" | "center" | "right" | null | undefined} alignment */
function alignmentAttribute(alignment) {
  return alignment ? ` style="text-align:${alignment}"` : "";
}

/**
 * @param {string[]} lines
 * @param {number} start
 * @param {RegExp} pattern
 */
function collectList(lines, start, pattern) {
  /** @type {string[]} */
  const items = [];
  let index = start;
  while (index < lines.length) {
    const match = pattern.exec(lines[index].trim());
    if (!match) {
      break;
    }
    items.push(match[1]);
    index += 1;
  }
  return { items, nextIndex: index };
}

/** @param {string} raw */
function renderInline(raw) {
  let escaped = escapeHtml(raw);
  escaped = escaped.replace(/`([^`]+)`/g, "<code>$1</code>");
  escaped = escaped.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  escaped = escaped.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  return escaped;
}

/** @param {string} raw */
function escapeHtml(raw) {
  return String(raw)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

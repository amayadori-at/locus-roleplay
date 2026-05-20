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

    const heading = /^(#{1,4})\s+(.+)$/.exec(trimmed);
    if (heading) {
      flushParagraph();
      const level = heading[1].length;
      html.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
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

import DOMPurify from "dompurify";

/**
 * Resolve a dot-separated path in a nested object.
 * Keys may contain ":" separators within a segment.
 * @param {string} path
 * @param {Record<string, any>} obj
 * @returns {any}
 */
export function resolveStateValue(path, obj) {
  const keys = path.trim().split(".");
  let current = obj;
  for (const key of keys) {
    if (current == null) return null;
    current = current[key];
  }
  return current;
}

/**
 * Replace {{ state.path }} placeholders with values from state.
 * Missing keys fall back to "-".
 * @param {string} html
 * @param {Record<string, any>} state
 * @returns {string}
 */
export function expandPlaceholders(html, state) {
  return html.replace(/\{\{\s*state\.([^}]+)\s*\}\}/g, (_match, path) => {
    const val = resolveStateValue(path, state);
    return val !== null && val !== undefined ? String(val) : "-";
  });
}

/**
 * Sanitize HTML using DOMPurify, forbidding tags and attributes that could
 * execute scripts or load external resources.
 * @param {string} html
 * @returns {string}
 */
export function sanitizeHtml(html) {
  return DOMPurify.sanitize(html, {
    FORBID_TAGS: ["script", "iframe", "object", "embed", "link"],
    FORBID_ATTR: ["style", "onclick", "onload", "onerror"],
  });
}

/**
 * Build the rendered HTML for a state template:
 * 1. Expand {{ state.xxx }} placeholders
 * 2. Process data-bind* attributes
 * 3. Sanitize with DOMPurify
 * @param {string} templateHtml
 * @param {Record<string, any>} state
 * @returns {string}
 */
export function buildRenderedHtml(templateHtml, state) {
  const html = expandPlaceholders(templateHtml, state);

  const parser = new DOMParser();
  const doc = parser.parseFromString(html, "text/html");
  const body = doc.body;

  body.querySelectorAll("[data-bind]").forEach((el) => {
    const path = el.getAttribute("data-bind") || "";
    const val = resolveStateValue(path, state);
    el.textContent = val !== null && val !== undefined ? String(val) : "-";
  });

  body.querySelectorAll("[data-bind-list]").forEach((el) => {
    const path = el.getAttribute("data-bind-list") || "";
    const val = resolveStateValue(path, state);
    if (Array.isArray(val) && val.length > 0) {
      el.innerHTML = "";
      val.forEach((item) => {
        const li = doc.createElement("li");
        li.textContent = String(item);
        el.appendChild(li);
      });
    }
  });

  body.querySelectorAll("[data-bind-meter]").forEach((el) => {
    const path = el.getAttribute("data-bind-meter") || "";
    const val = resolveStateValue(path, state);
    if (val !== null && val !== undefined) {
      el.setAttribute("value", String(val));
    }
  });

  body.querySelectorAll("[data-bind-bool]").forEach((el) => {
    const path = el.getAttribute("data-bind-bool") || "";
    const val = resolveStateValue(path, state);
    const isTrue = val === true || val === "true";
    el.classList.add(isTrue ? "is-true" : "is-false");
    el.setAttribute("data-value", isTrue ? "true" : "false");
  });

  return DOMPurify.sanitize(body.innerHTML, {
    FORBID_TAGS: ["script", "iframe", "object", "embed", "link"],
    FORBID_ATTR: ["style", "onclick", "onload", "onerror"],
  });
}

/**
 * @param {string} value
 * @param {number} start
 * @param {number} end
 * @param {"quote" | "asterisk"} mode
 */
export function wrapComposerSelection(value, start, end, mode) {
  const content = typeof value === "string" ? value : "";
  const safeStart = clampIndex(start, content.length);
  const safeEnd = clampIndex(end, content.length);
  const selectionStart = Math.min(safeStart, safeEnd);
  const selectionEnd = Math.max(safeStart, safeEnd);
  const before = content.slice(0, selectionStart);
  const selected = content.slice(selectionStart, selectionEnd);
  const after = content.slice(selectionEnd);
  const left = mode === "quote" ? "「" : "*";
  const right = mode === "quote" ? "」" : selected ? "*" : "";

  return {
    value: `${before}${left}${selected}${right}${after}`,
    cursor: selected ? selectionEnd + left.length + right.length : selectionStart + left.length
  };
}

/**
 * @param {{
 *   key?: string,
 *   shiftKey?: boolean,
 *   altKey?: boolean,
 *   ctrlKey?: boolean,
 *   metaKey?: boolean
 * }} event
 * @param {boolean} sendOnEnter
 */
export function shouldSubmitComposer(event, sendOnEnter) {
  if (event.key !== "Enter") return false;
  if (sendOnEnter) {
    return !event.shiftKey && !event.altKey && !event.ctrlKey && !event.metaKey;
  }
  return Boolean(event.ctrlKey || event.metaKey);
}

/**
 * @param {number} value
 * @param {number} max
 */
function clampIndex(value, max) {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(max, Math.trunc(value)));
}

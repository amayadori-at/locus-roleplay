/**
 * @param {string} block
 * @returns {{ event: string, data: any } | null}
 */
export function parseSseEvent(block) {
  let event = "message";
  const dataLines = [];
  for (const line of block.split(/\n/)) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice("data:".length).trimStart());
    }
  }
  if (!dataLines.length) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return null;
  }
}

/**
 * @param {Response} response
 * @param {{
 *   onEvent: (event: { event: string, data: any }) => void | "stop" | Promise<void | "stop">,
 *   createError?: (data: any) => Error
 * }} options
 */
export async function consumeSseStream(response, options) {
  if (!response.body) {
    throw new Error("Streaming response body is unavailable");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const parts = buffer.split(/\r?\n\r?\n/);
      buffer = parts.pop() || "";
      for (const part of parts) {
        const event = parseSseEvent(part);
        if (!event) continue;
        if (event.event === "error") {
          throw (options.createError?.(event.data) || new Error(String(event.data?.message || event.data?.error || "Stream failed")));
        }
        const action = await options.onEvent(event);
        if (action === "stop") {
          await reader.cancel().catch(() => {});
          return;
        }
      }
      if (done) break;
    }
  } finally {
    reader.releaseLock();
  }
}

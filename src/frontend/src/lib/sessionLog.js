/**
 * @param {Record<string, any>} message
 */
export function logMessageKey(message) {
  return `${message.turn ?? ""}:${message.role ?? ""}`;
}

/**
 * Prepend older log entries while keeping already-loaded messages stable.
 *
 * @template {Record<string, any>} T
 * @param {T[]} currentMessages
 * @param {T[]} olderMessages
 * @returns {T[]}
 */
export function mergeOlderLogMessages(currentMessages, olderMessages) {
  const existingKeys = new Set(currentMessages.map(logMessageKey));
  return [
    ...olderMessages.filter((message) => !existingKeys.has(logMessageKey(message))),
    ...currentMessages
  ];
}

/**
 * @param {Record<string, any>} currentPagination
 * @param {Record<string, any>} olderPagination
 */
export function mergeLogPagination(currentPagination, olderPagination) {
  return {
    ...olderPagination,
    max_turn: currentPagination.max_turn ?? olderPagination.max_turn,
    has_more_after: currentPagination.has_more_after ?? olderPagination.has_more_after,
  };
}

/**
 * @template {Record<string, any>} T
 * @param {T[]} messages
 * @param {string} userMessage
 * @param {boolean} useStream
 * @returns {Array<T | { role: string, content: string, streaming?: boolean }>}
 */
export function appendPendingTurnMessages(messages, userMessage, useStream) {
  const pendingUser = { role: "user", content: userMessage };
  if (!useStream) {
    return [...messages, pendingUser];
  }
  return [...messages, pendingUser, { role: "assistant", content: "", streaming: true }];
}

/**
 * @template {Record<string, any>} T
 * @param {T[]} messages
 * @param {string} delta
 * @returns {T[]}
 */
export function appendStreamingDeltaToMessages(messages, delta) {
  return messages.map((message, index) => {
    const isStreamingAssistant = index === messages.length - 1 && message.role === "assistant" && message.streaming;
    return isStreamingAssistant ? { ...message, content: `${message.content || ""}${delta}` } : message;
  });
}

/**
 * @template {Record<string, any>} T
 * @param {T[]} messages
 * @param {string} userMessage
 * @param {Record<string, any>} turn
 * @param {boolean} usedStream
 * @returns {Array<T | { role: string, content: string, segments?: Array<Record<string, any>>, turn: number, response_duration_ms?: number, timings_ms?: Record<string, number> }>}
 */
export function finalizeTurnMessages(messages, userMessage, turn, usedStream) {
  const pendingCount = usedStream ? 2 : 1;
  return [
    ...messages.slice(0, -pendingCount),
    { role: "user", content: userMessage, turn: turn.turn },
    {
      role: "assistant",
      content: turn.assistant_content || "",
      segments: turn.segments || [],
      turn: turn.turn,
      response_duration_ms: turn.response_duration_ms,
      timings_ms: turn.timings_ms
    }
  ];
}

/**
 * @template {Record<string, any>} T
 * @param {T[]} messages
 * @param {string} userMessage
 * @returns {T[]}
 */
export function removePendingTurnMessages(messages, userMessage) {
  return messages.filter((message, index) => {
    const isTrailingAssistant = index === messages.length - 1 && message.role === "assistant" && message.streaming;
    const isTrailingUser =
      index >= messages.length - 2 && message.role === "user" && message.content === userMessage && !message.turn;
    return !isTrailingAssistant && !isTrailingUser;
  });
}

/**
 * @template {Record<string, any>} T
 * @param {T[]} messages
 * @param {number} turn
 * @param {string} content
 * @returns {T[]}
 */
export function updateRegeneratingAssistantMessage(messages, turn, content) {
  return messages.map((message) => {
    if (message.role !== "assistant" || message.turn !== turn) {
      return message;
    }
    const updated = { ...message, content, streaming: true };
    delete updated.segments;
    delete updated.response_duration_ms;
    delete updated.timings_ms;
    return updated;
  });
}

/**
 * @template {Record<string, any>} T
 * @param {T[]} messages
 * @param {number} sourceTurn
 * @param {string} content
 * @returns {Array<T | { role: string, content: string, streaming: boolean, continued_from_turn: number }>}
 */
export function updateStreamingContinuedAssistantMessage(messages, sourceTurn, content) {
  const last = messages[messages.length - 1];
  if (
    last &&
    last.role === "assistant" &&
    last.streaming &&
    last.continued_from_turn === sourceTurn
  ) {
    return [
      ...messages.slice(0, -1),
      {
        ...last,
        content,
        streaming: true,
        continued_from_turn: sourceTurn
      }
    ];
  }
  return [
    ...messages,
    {
      role: "assistant",
      content,
      streaming: true,
      continued_from_turn: sourceTurn
    }
  ];
}

/**
 * @param {Record<string, any>} message
 * @returns {string}
 */
export function formatResponseDuration(message) {
  const timings = responseTimings(message);
  const parts = [];
  if (Number.isFinite(timings.rag_search_ms)) parts.push(`RAG ${formatDurationMs(timings.rag_search_ms)}`);
  if (Number.isFinite(timings.rp_model_ms)) parts.push(`RP ${formatDurationMs(timings.rp_model_ms)}`);
  if (Number.isFinite(timings.state_model_ms)) parts.push(`State ${formatDurationMs(timings.state_model_ms)}`);
  if (parts.length) return parts.join(" / ");
  const value = message?.response_duration_ms;
  if (!Number.isFinite(value) || value < 0) return "";
  return `LLM ${formatDurationMs(value)}`;
}

/**
 * @param {Record<string, any>} message
 * @returns {Record<string, number>}
 */
function responseTimings(message) {
  const raw = message?.timings_ms;
  if (!raw || typeof raw !== "object") return {};
  /** @type {Record<string, number>} */
  const timings = {};
  for (const [key, value] of Object.entries(raw)) {
    if (typeof value === "number" && Number.isFinite(value) && value >= 0) timings[key] = value;
  }
  return timings;
}

/**
 * @param {number} value
 * @returns {string}
 */
function formatDurationMs(value) {
  const milliseconds = Math.round(value);
  if (milliseconds < 1000) return `${milliseconds}ms`;
  const seconds = milliseconds / 1000;
  return `${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)}s`;
}

/**
 * @param {Record<string, any>} message
 * @param {"prev" | "next"} direction
 */
export function nextAssistantCandidateIndex(message, direction) {
  const candidates = Array.isArray(message.candidates) ? message.candidates : [];
  if (candidates.length < 2) return null;
  const current = Number.isInteger(message.active_candidate_index) ? message.active_candidate_index : 0;
  const normalized = ((current % candidates.length) + candidates.length) % candidates.length;
  return direction === "prev"
    ? (normalized - 1 + candidates.length) % candidates.length
    : (normalized + 1) % candidates.length;
}

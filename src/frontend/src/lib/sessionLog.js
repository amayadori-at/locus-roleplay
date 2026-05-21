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
 * @returns {Array<T | { role: string, content: string, segments?: Array<Record<string, any>>, turn: number }>}
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
      turn: turn.turn
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
    return updated;
  });
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

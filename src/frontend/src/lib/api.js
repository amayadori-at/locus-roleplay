import { consumeSseStream } from "./sse.js";

const JSON_HEADERS = { "Content-Type": "application/json" };

export class ApiError extends Error {
  /**
   * @param {string} message
   * @param {number} status
   * @param {unknown} payload
   */
  constructor(message, status, payload) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

/**
 * @param {string} path
 * @param {RequestInit} [options]
 * @returns {Promise<any>}
 */
export async function apiJson(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...JSON_HEADERS,
      ...(options.headers || {})
    }
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    if (payload && typeof payload === "object") {
      if ("message" in payload) {
        message = String(payload.message);
      } else if ("error" in payload) {
        message = String(payload.error);
      }
    }
    throw new ApiError(message, response.status, payload);
  }
  return payload;
}

/**
 * @param {string} path
 * @param {any} payload
 */
function apiPost(path, payload) {
  return apiJson(path, { method: "POST", body: JSON.stringify(payload) });
}

/**
 * @param {string} path
 * @param {any} payload
 */
function apiPut(path, payload) {
  return apiJson(path, { method: "PUT", body: JSON.stringify(payload) });
}

export function getHealth() {
  return apiJson("/api/health");
}

export function listScenarios() {
  return apiJson("/api/scenarios");
}

/**
 * @param {{ scenario_id: string, name: string, description?: string }} payload
 */
export function createScenario(payload) {
  return apiJson("/api/scenarios", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function listPersonas() {
  return apiJson("/api/personas");
}

/**
 * @param {string} personaId
 */
export function getPersona(personaId) {
  return apiJson(`/api/personas/${encodeURIComponent(personaId)}`);
}

/**
 * @param {string} personaId
 * @param {string} content
 */
export function updatePersona(personaId, content) {
  return apiPut(`/api/personas/${encodeURIComponent(personaId)}`, { content });
}

/**
 * @param {string} personaId
 * @param {string} name
 */
export function createPersona(personaId, name) {
  return apiPost("/api/personas", { persona_id: personaId, name });
}

export function listProfiles() {
  return apiJson("/api/profiles");
}

/**
 * @param {string} profileId
 */
export function getProfile(profileId) {
  return apiJson(`/api/profiles/${encodeURIComponent(profileId)}`);
}

/**
 * @param {string} profileId
 * @param {Record<string, any>} patch
 */
export function updateProfile(profileId, patch) {
  return apiPut(`/api/profiles/${encodeURIComponent(profileId)}`, patch);
}

/**
 * @param {string} scenarioId
 */
export function listScenarioSourceFiles(scenarioId) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/source`);
}

/**
 * @param {string} scenarioId
 */
export function listScenarioStartings(scenarioId) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/startings`);
}

/**
 * @param {string} scenarioId
 */
export function listScenarioCharacterBustups(scenarioId) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/character-bustups`);
}

/**
 * @param {string} scenarioId
 * @param {string} path
 */
export function getScenarioSourceFile(scenarioId, path) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/source?path=${encodeURIComponent(path)}`);
}

/**
 * @param {string} scenarioId
 * @param {string} path
 * @param {string} content
 */
export function createScenarioSourceFile(scenarioId, path, content) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/source`, {
    method: "POST",
    body: JSON.stringify({ path, content })
  });
}

/**
 * @param {string} scenarioId
 * @param {string} path
 * @param {string} content
 */
export function updateScenarioSourceFile(scenarioId, path, content) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/source`, {
    method: "PUT",
    body: JSON.stringify({ path, content })
  });
}

/**
 * @param {string} scenarioId
 * @param {string} path
 */
export function deleteScenarioSourceFile(scenarioId, path) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/source?path=${encodeURIComponent(path)}`, {
    method: "DELETE"
  });
}

/**
 * @param {string} scenarioId
 */
export function listScenarioStarts(scenarioId) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/starts`);
}

/**
 * @param {string} scenarioId
 * @param {{ id: string, name: string, body?: string }} payload
 */
export function createScenarioStart(scenarioId, payload) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/starts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

/**
 * @param {string} scenarioId
 * @param {string} startId
 */
export function deleteScenarioStart(scenarioId, startId) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/starts/${encodeURIComponent(startId)}`, {
    method: "DELETE"
  });
}

/**
 * @param {string} scenarioId
 */
export function getScenarioSettings(scenarioId) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/settings`);
}

/**
 * @param {string} scenarioId
 * @param {{ prompt_graph_mode: string }} settings
 */
export function updateScenarioSettings(scenarioId, settings) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings)
  });
}

/**
 * @param {string} scenarioId
 * @param {string} startId
 */
export function getStartPromptGraph(scenarioId, startId) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/starts/${encodeURIComponent(startId)}/prompt-graph`);
}

/**
 * @param {string} scenarioId
 * @param {string} startId
 * @param {Record<string, any>} graph
 */
export function updateStartPromptGraph(scenarioId, startId, graph) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/starts/${encodeURIComponent(startId)}/prompt-graph`, {
    method: "PUT",
    body: JSON.stringify({ graph })
  });
}

/**
 * @param {string} scenarioId
 * @param {string} startId
 */
export function getStartManifest(scenarioId, startId) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/starts/${encodeURIComponent(startId)}/manifest`);
}

/**
 * @param {string} scenarioId
 * @param {string} startId
 * @param {{ name: string, description: string, lore_include: string[], lore_exclude: string[], initial_state_path: string | null }} manifest
 */
export function updateStartManifest(scenarioId, startId, manifest) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/starts/${encodeURIComponent(startId)}/manifest`, {
    method: "PUT",
    body: JSON.stringify(manifest)
  });
}

/**
 * @param {string} scenarioId
 */
export function getScenarioPromptGraph(scenarioId) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/prompt-graph`);
}

/**
 * @param {string} scenarioId
 * @param {Record<string, any>} graph
 */
export function updateScenarioPromptGraph(scenarioId, graph) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/prompt-graph`, {
    method: "PUT",
    body: JSON.stringify({ graph })
  });
}

/**
 * @param {string} scenarioId
 * @param {{
 *   session_id?: string,
 *   starting_id?: string,
 *   persona_id?: string,
 *   profile_id?: string,
 *   user_message: string,
 *   user_note?: string,
 *   session_note?: string,
 *   scene_note?: string
 * }} params
 */
export function getScenarioPromptPreview(scenarioId, params) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && String(value).trim() !== "") {
      query.set(key, String(value));
    }
  }
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/prompt-preview?${query.toString()}`);
}

/**
 * @param {string} scenarioId
 * @param {string} [sessionId]
 */
export function getScenarioState(scenarioId, sessionId) {
  if (sessionId) {
    return apiJson(
      `/api/scenarios/${encodeURIComponent(scenarioId)}/sessions/${encodeURIComponent(sessionId)}/state`
    );
  }
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/state`);
}

/**
 * @param {string} scenarioId
 */
export function getScenarioStateTemplate(scenarioId) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/state/template`);
}

/**
 * @param {string} scenarioId
 */
export function getScenarioRagStatus(scenarioId) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/rag/status`);
}

/**
 * @param {string} scenarioId
 * @param {string} [sessionId]
 */
export function listScenarioMemory(scenarioId, sessionId) {
  const query = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : "";
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/memory${query}`);
}

/**
 * @param {string} scenarioId
 * @param {string} kind
 * @param {string} memoryId
 * @param {{ rag_enabled?: boolean, status?: string }} patch
 */
export function updateMemoryMetadata(scenarioId, kind, memoryId, patch) {
  return apiPut(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/memory/${encodeURIComponent(kind)}/${encodeURIComponent(memoryId)}`,
    patch
  );
}

/**
 * @param {string} scenarioId
 */
export function listMemoryConsolidationSuggestions(scenarioId) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/memory/consolidation-suggestions`);
}

/**
 * @param {string} scenarioId
 * @param {{ session_id: string, profile_id: string }} payload
 */
export function createMemoryConsolidationSuggestions(scenarioId, payload) {
  return apiPost(`/api/scenarios/${encodeURIComponent(scenarioId)}/memory/consolidation-suggestions`, payload);
}

/**
 * @param {string} scenarioId
 * @param {string} suggestionId
 * @param {string} status
 */
export function updateMemoryConsolidationSuggestionStatus(scenarioId, suggestionId, status) {
  return apiPut(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/memory/consolidation-suggestions/${encodeURIComponent(suggestionId)}`,
    { status }
  );
}

/**
 * @param {string} scenarioId
 * @param {string} suggestionId
 */
export function applyMemoryConsolidationSuggestion(scenarioId, suggestionId) {
  return apiPut(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/memory/consolidation-suggestions/${encodeURIComponent(suggestionId)}`,
    { apply: true }
  );
}

/**
 * @param {string} scenarioId
 */
export function rebuildScenarioRagIndex(scenarioId) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/rag/rebuild`, {
    method: "POST",
    body: JSON.stringify({})
  });
}

/**
 * @param {string} scenarioId
 */
export function getScenarioRagVectorStatus(scenarioId) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/rag/vector-status`);
}

/**
 * @param {string} scenarioId
 */
export function rebuildScenarioVectorIndex(scenarioId) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/rag/rebuild-vectors`, {
    method: "POST",
    body: JSON.stringify({})
  });
}

/**
 * @param {string} scenarioId
 * @param {string} sessionId
 */
export function getSessionPins(scenarioId, sessionId) {
  return apiJson(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/sessions/${encodeURIComponent(sessionId)}/pins`
  );
}

/**
 * @param {string} scenarioId
 * @param {string} sessionId
 * @param {{ active_mods?: string[], pinned_characters?: string[] }} pins
 */
export function updateSessionPins(scenarioId, sessionId, pins) {
  return apiJson(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/sessions/${encodeURIComponent(sessionId)}/pins`,
    { method: "PUT", body: JSON.stringify(pins) }
  );
}

/**
 * @param {string} scenarioId
 * @param {string} sessionId
 * @param {string | null} startingId
 */
export function updateSessionStarting(scenarioId, sessionId, startingId) {
  return apiJson(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/sessions/${encodeURIComponent(sessionId)}/starting`,
    { method: "PUT", body: JSON.stringify({ starting_id: startingId }) }
  );
}

/**
 * @param {string} scenarioId
 */
export function listScenarioSessions(scenarioId) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/sessions`);
}

/**
 * @param {string} scenarioId
 * @param {string} sessionId
 */
export function deleteSession(scenarioId, sessionId) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE"
  });
}

/**
 * @param {string} scenarioId
 * @param {string} sessionId
 */
export function getSessionDetail(scenarioId, sessionId) {
  return apiJson(`/api/scenarios/${encodeURIComponent(scenarioId)}/sessions/${encodeURIComponent(sessionId)}`);
}

/**
 * @param {{
 *   scenario_id: string,
 *   persona_id: string,
 *   rp_profile_id: string,
 *   summary_profile_id?: string | null,
 *   session_id?: string,
 *   display_name?: string,
 *   starting_id?: string | null
 * }} payload
 */
export function createSession(payload) {
  return apiJson("/api/sessions", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

/**
 * @param {string} scenarioId
 * @param {string} sessionId
 * @param {{ branched_from_turn: number, display_name?: string, session_id?: string }} payload
 */
export function createBranchSession(scenarioId, sessionId, payload) {
  return apiJson(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/sessions/${encodeURIComponent(sessionId)}/branches`,
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

/**
 * @param {string} scenarioId
 * @param {string} sessionId
 * @param {{ turnLimit?: number, beforeTurn?: number, fromTurn?: number }} [options]
 */
export function getSessionLog(scenarioId, sessionId, options = {}) {
  const query = new URLSearchParams();
  if (options.turnLimit) {
    query.set("turn_limit", String(options.turnLimit));
  }
  if (options.beforeTurn !== undefined && options.beforeTurn !== null) {
    query.set("before_turn", String(options.beforeTurn));
  }
  if (options.fromTurn !== undefined && options.fromTurn !== null) {
    query.set("from_turn", String(options.fromTurn));
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiJson(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/sessions/${encodeURIComponent(sessionId)}/log${suffix}`
  );
}

/**
 * @param {string} scenarioId
 * @param {string} sessionId
 */
export function getSessionPromptPreview(scenarioId, sessionId) {
  return apiJson(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/sessions/${encodeURIComponent(sessionId)}/prompt/latest`
  );
}

/**
 * @param {string} scenarioId
 * @param {string} sessionId
 */
export function getSessionTimeline(scenarioId, sessionId) {
  return apiJson(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/sessions/${encodeURIComponent(sessionId)}/timeline`
  );
}

/**
 * @param {string} scenarioId
 * @param {string} sessionId
 * @param {string} jobId
 */
export function getPostprocessJob(scenarioId, sessionId, jobId) {
  return apiJson(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/sessions/${encodeURIComponent(sessionId)}/postprocess/${encodeURIComponent(jobId)}`
  );
}

/**
 * @param {string} scenarioId
 * @param {string} sessionId
 * @param {string} turnId
 */
export function getTurnJob(scenarioId, sessionId, turnId) {
  return apiJson(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/sessions/${encodeURIComponent(sessionId)}/turns/${encodeURIComponent(turnId)}`
  );
}

/**
 * @param {string} scenarioId
 * @param {string} sessionId
 * @param {{ user_note?: string, session_note?: string, scene_note?: string, display_name?: string, bookmarked_turns?: number[], rp_profile_id?: string, summary_profile_id?: string }} payload
 */
export function updateSessionSettings(scenarioId, sessionId, payload) {
  return apiJson(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/sessions/${encodeURIComponent(sessionId)}/settings`,
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
}

/**
 * @param {string} scenarioId
 * @param {string} sessionId
 * @param {string} userMessage
 * @param {{ signal?: AbortSignal, stream?: boolean, async?: boolean, deferPostprocess?: boolean }} [options]
 */
export function sendTurn(scenarioId, sessionId, userMessage, options = {}) {
  return apiJson(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/sessions/${encodeURIComponent(sessionId)}/turns`,
    {
      method: "POST",
      signal: options.signal,
      body: JSON.stringify({
        user_message: userMessage,
        stream: Boolean(options.stream),
        async: Boolean(options.async),
        defer_postprocess: Boolean(options.deferPostprocess)
      })
    }
  );
}

/**
 * @param {string} scenarioId
 * @param {string} sessionId
 * @param {string} userMessage
 * @param {{
 *   signal?: AbortSignal,
 *   onDelta?: (delta: string) => void,
 *   onFinal?: (data: any) => void,
 *   onPostTurn?: (data: any) => void | Promise<void>
 * }} [options]
 */
export async function sendTurnStream(scenarioId, sessionId, userMessage, options = {}) {
  const response = await fetch(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/sessions/${encodeURIComponent(sessionId)}/turns`,
    {
      method: "POST",
      headers: JSON_HEADERS,
      signal: options.signal,
      body: JSON.stringify({ user_message: userMessage, stream: true })
    }
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    let message = `HTTP ${response.status}`;
    if (payload && typeof payload === "object") {
      if ("message" in payload) {
        message = String(payload.message);
      } else if ("error" in payload) {
        message = String(payload.error);
      }
    }
    throw new ApiError(message, response.status, payload);
  }
  if (!response.body) {
    throw new ApiError("Streaming response body is unavailable", response.status, {});
  }

  /** @type {any} */
  let finalData = null;
  await consumeSseStream(response, {
    createError: (data) => new ApiError(String(data.message || data.error || "Stream failed"), 200, data),
    async onEvent(event) {
      if (event.event === "delta" && typeof event.data.delta === "string") {
        options.onDelta?.(event.data.delta);
      } else if (event.event === "final") {
        finalData = event.data;
        options.onFinal?.(event.data);
      } else if (event.event === "post_turn") {
        await options.onPostTurn?.(event.data);
        return "stop";
      }
    }
  });
  if (finalData) return finalData;
  throw new ApiError("Streaming response did not include final turn payload", response.status, {});
}

/**
 * @param {string} scenarioId
 * @param {string} sessionId
 * @param {number} turn
 * @param {string} role
 * @param {string} content
 */
export function updateSessionMessage(scenarioId, sessionId, turn, role, content) {
  return apiJson(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/sessions/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(turn)}/${encodeURIComponent(role)}`,
    {
      method: "PUT",
      body: JSON.stringify({ content })
    }
  );
}

/**
 * @param {string} scenarioId
 * @param {string} sessionId
 * @param {number} turn
 * @param {string} role
 * @param {boolean} rewind
 */
export function deleteSessionMessage(scenarioId, sessionId, turn, role, rewind = false) {
  const query = rewind ? "?rewind=true" : "";
  return apiJson(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/sessions/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(turn)}/${encodeURIComponent(role)}${query}`,
    {
      method: "DELETE"
    }
  );
}

/**
 * @param {string} scenarioId
 * @param {string} sessionId
 * @param {number} turn
 * @param {number} candidateIndex
 */
export function switchAssistantCandidate(scenarioId, sessionId, turn, candidateIndex) {
  return apiJson(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/sessions/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(turn)}/assistant/candidate`,
    {
      method: "PUT",
      body: JSON.stringify({ candidate_index: candidateIndex })
    }
  );
}

/**
 * @param {string} scenarioId
 * @param {string} sessionId
 * @param {number} turn
 * @param {{ signal?: AbortSignal, stream?: boolean }} [options]
 */
export function regenerateTurn(scenarioId, sessionId, turn, options = {}) {
  return apiJson(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/sessions/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(turn)}/regenerate`,
    {
      method: "POST",
      signal: options.signal,
      body: JSON.stringify({ stream: Boolean(options.stream) })
    }
  );
}

/**
 * @param {string} scenarioId
 * @param {string} sessionId
 * @param {number} turn
 * @param {{ signal?: AbortSignal, onDelta?: (delta: string) => void }} [options]
 */
export async function regenerateTurnStream(scenarioId, sessionId, turn, options = {}) {
  const response = await fetch(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/sessions/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(turn)}/regenerate`,
    {
      method: "POST",
      headers: JSON_HEADERS,
      signal: options.signal,
      body: JSON.stringify({ stream: true })
    }
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    let message = `HTTP ${response.status}`;
    if (payload && typeof payload === "object") {
      if ("message" in payload) {
        message = String(payload.message);
      } else if ("error" in payload) {
        message = String(payload.error);
      }
    }
    throw new ApiError(message, response.status, payload);
  }
  if (!response.body) {
    throw new ApiError("Streaming response body is unavailable", response.status, {});
  }

  /** @type {any} */
  let finalData = null;
  await consumeSseStream(response, {
    createError: (data) => new ApiError(String(data.message || data.error || "Stream failed"), 200, data),
    onEvent(event) {
      if (event.event === "delta" && typeof event.data.delta === "string") {
        options.onDelta?.(event.data.delta);
      } else if (event.event === "final") {
        finalData = event.data;
        return "stop";
      }
    }
  });
  if (finalData) return finalData;
  throw new ApiError("Streaming response did not include final turn payload", response.status, {});
}

/**
 * @param {string} scenarioId
 * @param {string} sessionId
 * @param {number} turn
 * @param {{ signal?: AbortSignal, stream?: boolean }} [options]
 */
export function continueTurn(scenarioId, sessionId, turn, options = {}) {
  return apiJson(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/sessions/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(turn)}/continue`,
    {
      method: "POST",
      signal: options.signal,
      body: JSON.stringify({ stream: Boolean(options.stream) })
    }
  );
}

/**
 * @param {string} scenarioId
 * @param {string} sessionId
 * @param {number} turn
 * @param {{ signal?: AbortSignal, onDelta?: (delta: string) => void }} [options]
 */
export async function continueTurnStream(scenarioId, sessionId, turn, options = {}) {
  const response = await fetch(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/sessions/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(turn)}/continue`,
    {
      method: "POST",
      headers: JSON_HEADERS,
      signal: options.signal,
      body: JSON.stringify({ stream: true })
    }
  );
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    let message = `HTTP ${response.status}`;
    if (payload && typeof payload === "object") {
      if ("message" in payload) {
        message = String(payload.message);
      } else if ("error" in payload) {
        message = String(payload.error);
      }
    }
    throw new ApiError(message, response.status, payload);
  }
  if (!response.body) {
    throw new ApiError("Streaming response body is unavailable", response.status, {});
  }

  /** @type {any} */
  let finalData = null;
  await consumeSseStream(response, {
    createError: (data) => new ApiError(String(data.message || data.error || "Stream failed"), 200, data),
    onEvent(event) {
      if (event.event === "delta" && typeof event.data.delta === "string") {
        options.onDelta?.(event.data.delta);
      } else if (event.event === "final") {
        finalData = event.data;
        return "stop";
      }
    }
  });
  if (finalData) return finalData;
  throw new ApiError("Streaming response did not include final turn payload", response.status, {});
}

// ---------------------------------------------------------------------------
// ZIP export / import
// ---------------------------------------------------------------------------

/**
 * @param {string} scenarioId
 * @returns {Promise<Blob>}
 */
export async function exportScenario(scenarioId) {
  const resp = await fetch(`/api/scenarios/${encodeURIComponent(scenarioId)}/export`);
  if (!resp.ok) {
    let message = `Export failed: ${resp.status}`;
    try {
      const data = await resp.json();
      if (data.message) message = data.message;
    } catch (_) { /* ignore */ }
    throw new ApiError(message, resp.status, {});
  }
  return resp.blob();
}

/**
 * @param {Blob} zipBlob
 * @param {string} scenarioId
 * @returns {Promise<any>}
 */
export async function importScenario(zipBlob, scenarioId) {
  const resp = await fetch(
    `/api/scenarios/import?scenario_id=${encodeURIComponent(scenarioId)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: zipBlob,
    }
  );
  const data = await resp.json();
  if (!resp.ok) throw new ApiError(data.message || data.error || `Import failed: ${resp.status}`, resp.status, data);
  return data;
}

// ---------------------------------------------------------------------------
// Memory management
// ---------------------------------------------------------------------------

/**
 * @param {string} scenarioId
 * @param {string} kind
 * @param {string} memoryId
 * @returns {Promise<any>}
 */
export async function deleteMemory(scenarioId, kind, memoryId) {
  const resp = await fetch(
    `/api/scenarios/${encodeURIComponent(scenarioId)}/memory/${encodeURIComponent(kind)}/${encodeURIComponent(memoryId)}`,
    { method: "DELETE" }
  );
  const data = await resp.json();
  if (!resp.ok) throw new ApiError(data.message || data.error || "Delete failed", resp.status, data);
  return data;
}

import { tick } from "svelte";
import { get } from "svelte/store";
import {
  continueTurn,
  continueTurnStream,
  getPostprocessJob,
  getSessionDetail,
  getTurnJob,
  regenerateTurn,
  regenerateTurnStream,
  sendTurn,
  sendTurnStream
} from "../api.js";
import {
  appendPendingTurnMessages,
  appendStreamingDeltaToMessages,
  finalizeTurnMessages,
  removePendingTurnMessages,
  updateRegeneratingAssistantMessage,
  updateStreamingContinuedAssistantMessage
} from "../sessionLog.js";
import { translateNow } from "../i18n.js";

/**
 * Turn engine for SessionPage: owns the chat message list and all turn
 * submission / polling / SSE-resume machinery as $state, so the page and
 * ChatPanel only read state and call actions.
 *
 * @param {{
 *   preferences: any,
 *   loadLog: (scenarioId: string, sessionId: string) => Promise<void>,
 *   loadTimeline: (scenarioId: string, sessionId: string) => Promise<void>,
 *   loadState: (scenarioId: string, sessionId?: string) => Promise<void>,
 *   reloadSession: (scenarioId: string, sessionId: string, opts?: Record<string, boolean>) => Promise<void>,
 *   scrollToBottom: () => Promise<void> | void,
 *   refreshSettingsPanes?: () => Promise<unknown> | void,
 * }} deps
 */
export function createTurnEngine(deps) {
  /** @type {Array<Record<string, any>>} */
  let messages = $state([]);
  let sending = $state(false);
  let stateUpdating = $state(false);
  let turnJobPolling = $state(false);
  let turnNotice = $state("");
  let error = $state("");
  let input = $state("");
  let newMessageBadge = $state(false);

  /** @type {AbortController | null} */
  let turnAbortController = null;
  /** @type {ReturnType<typeof setTimeout> | null} */
  let postprocessPollTimer = null;
  /** @type {ReturnType<typeof setTimeout> | null} */
  let turnPollTimer = null;

  /**
   * @param {string} scenarioId
   * @param {string} sessionId
   */
  async function submitTurn(scenarioId, sessionId) {
    const userMessage = input.trim();
    if (!scenarioId || !sessionId || !userMessage || sending || stateUpdating) {
      return;
    }
    const controller = new AbortController();
    turnAbortController = controller;
    input = "";
    error = "";
    turnNotice = "";
    newMessageBadge = false;
    sending = true;
    turnJobPolling = false;
    const useStream = get(deps.preferences).streamEnabled;
    messages = appendPendingTurnMessages(messages, userMessage, useStream);
    let streamFinalReceived = false;
    let postprocessPending = false;
    try {
      if (useStream) {
        await sendTurnStream(scenarioId, sessionId, userMessage, {
          signal: controller.signal,
          onDelta: appendStreamingDelta,
          onFinal: (data) => {
            streamFinalReceived = true;
            const turn = data.turn;
            messages = finalizeTurnMessages(messages, userMessage, turn, true);
            stateUpdating = true;
            void deps.loadTimeline(scenarioId, sessionId);
            void deps.refreshSettingsPanes?.();
            if (turnAbortController === controller) {
              turnAbortController = null;
              sending = false;
            }
          },
          onPostTurn: async (data) => {
            await handlePostTurnResult(scenarioId, sessionId, data);
          }
        });
      } else {
        const payload = await sendTurn(scenarioId, sessionId, userMessage, {
          signal: controller.signal,
          stream: false,
          async: true,
          deferPostprocess: true
        });
        const job = payload.turn_job;
        if (turnAbortController === controller) {
          turnAbortController = null;
        }
        if (!job || typeof job.turn_id !== "string") {
          throw new Error(translateNow("session.turnJobMissing"));
        }
        await pollTurnJob(scenarioId, sessionId, job.turn_id, userMessage);
      }
    } catch (caught) {
      if (isAbortError(caught)) {
        if (!streamFinalReceived && controller.signal.reason === "user") {
          messages = removePendingTurnMessages(messages, userMessage);
          input = userMessage;
          turnNotice = translateNow("session.stopNotice");
        }
      } else {
        error = caught instanceof Error ? caught.message : translateNow("session.sendError");
      }
    } finally {
      if (turnAbortController === controller) {
        turnAbortController = null;
        sending = false;
      }
      if (!useStream && !postprocessPending) {
        stateUpdating = false;
      }
    }
  }

  /**
   * @param {string} scenarioId
   * @param {string} sessionId
   */
  async function resumePendingJobs(scenarioId, sessionId) {
    const payload = await getSessionDetail(scenarioId, sessionId);
    const pendingTurn = payload.pending_turn;
    const pendingPostprocess = payload.pending_postprocess;
    if (pendingTurn && typeof pendingTurn.turn_id === "string") {
      sending = true;
      turnNotice = translateNow("session.resumePendingTurn");
      void pollTurnJob(scenarioId, sessionId, pendingTurn.turn_id);
      return;
    }
    if (pendingPostprocess && typeof pendingPostprocess.job_id === "string") {
      stateUpdating = true;
      turnNotice = translateNow("session.resumePendingPostprocess");
      void handlePostTurnResult(scenarioId, sessionId, { postprocess_job: pendingPostprocess });
    }
  }

  /** @param {string} delta */
  function appendStreamingDelta(delta) {
    messages = appendStreamingDeltaToMessages(messages, delta);
  }

  /**
   * @param {string} scenarioId
   * @param {string} sessionId
   * @param {string} turnId
   * @param {string} [userMessage]
   */
  async function pollTurnJob(scenarioId, sessionId, turnId, userMessage = "") {
    clearTurnPollTimer();
    sending = true;
    turnJobPolling = true;
    for (let attempt = 0; attempt < 240; attempt += 1) {
      try {
        const payload = await getTurnJob(scenarioId, sessionId, turnId);
        const job = payload.turn_job || {};
        if (job.status === "completed") {
          const result = job.result || {};
          const turn = result.turn || result;
          const postprocessJob = result.postprocess_job;
          sending = false;
          turnJobPolling = false;
          newMessageBadge = true;
          if (userMessage && turn && typeof turn === "object") {
            messages = finalizeTurnMessages(messages, userMessage, turn, false);
          } else {
            await deps.loadLog(scenarioId, sessionId);
          }
          await deps.loadTimeline(scenarioId, sessionId);
          if (postprocessJob && typeof postprocessJob.job_id === "string") {
            stateUpdating = true;
            await handlePostTurnResult(scenarioId, sessionId, { postprocess_job: postprocessJob });
          } else {
            turnNotice = formatPostTurnNotice(turn);
            await deps.loadState(scenarioId, sessionId);
          }
          await deps.refreshSettingsPanes?.();
          return;
        }
        if (job.status === "failed") {
          const message = job.error?.message ? String(job.error.message) : translateNow("session.sendError");
          error = message;
          sending = false;
          turnJobPolling = false;
          return;
        }
      } catch (caught) {
        turnNotice = caught instanceof Error ? caught.message : translateNow("session.turnJobCheckError");
        sending = false;
        turnJobPolling = false;
        return;
      }
      await waitForTurnPoll(1000);
    }
    turnNotice = translateNow("session.turnJobPending");
    sending = false;
    turnJobPolling = false;
  }

  /**
   * @param {string} scenarioId
   * @param {string} sessionId
   * @param {Record<string, any>} data
   */
  async function handlePostTurnResult(scenarioId, sessionId, data) {
    const job = data?.postprocess_job;
    if (job && typeof job.job_id === "string") {
      await pollPostprocessJob(scenarioId, sessionId, job.job_id);
      return;
    }
    turnNotice = formatPostTurnNotice(data);
    stateUpdating = false;
    await Promise.all([deps.loadState(scenarioId, sessionId), deps.loadTimeline(scenarioId, sessionId)]);
  }

  /**
   * @param {string} scenarioId
   * @param {string} sessionId
   * @param {string} jobId
   */
  async function pollPostprocessJob(scenarioId, sessionId, jobId) {
    clearPostprocessPollTimer();
    stateUpdating = true;
    for (let attempt = 0; attempt < 120; attempt += 1) {
      try {
        const payload = await getPostprocessJob(scenarioId, sessionId, jobId);
        const job = payload.postprocess_job || {};
        if (job.status === "completed") {
          turnNotice = formatPostTurnNotice(job.result);
          stateUpdating = false;
          await Promise.all([deps.loadState(scenarioId, sessionId), deps.loadTimeline(scenarioId, sessionId)]);
          return;
        }
        if (job.status === "failed") {
          const message = job.error?.message ? String(job.error.message) : translateNow("session.postprocessError");
          turnNotice = translateNow("session.postprocessFailed", { message });
          stateUpdating = false;
          return;
        }
      } catch (caught) {
        turnNotice = caught instanceof Error ? caught.message : translateNow("session.postprocessCheckError");
        stateUpdating = false;
        return;
      }
      await waitForPostprocessPoll(1000);
    }
    turnNotice = translateNow("session.postprocessPending");
    stateUpdating = false;
  }

  /** @param {number} delayMs */
  function waitForPostprocessPoll(delayMs) {
    return new Promise((resolve) => {
      postprocessPollTimer = setTimeout(() => {
        postprocessPollTimer = null;
        resolve(undefined);
      }, delayMs);
    });
  }

  function clearPostprocessPollTimer() {
    if (postprocessPollTimer) {
      clearTimeout(postprocessPollTimer);
      postprocessPollTimer = null;
    }
  }

  /** @param {number} delayMs */
  function waitForTurnPoll(delayMs) {
    return new Promise((resolve) => {
      turnPollTimer = setTimeout(() => {
        turnPollTimer = null;
        resolve(undefined);
      }, delayMs);
    });
  }

  function clearTurnPollTimer() {
    if (turnPollTimer) {
      clearTimeout(turnPollTimer);
      turnPollTimer = null;
    }
  }

  /** @param {Record<string, any> | null | undefined} result */
  function formatPostTurnNotice(result) {
    if (!result || typeof result !== "object") return "";
    const warnings = [];
    if (typeof result.state_update_error === "string" && result.state_update_error) {
      warnings.push(translateNow("session.stateUpdateError"));
    }
    if (typeof result.memory_update_error === "string" && result.memory_update_error) {
      warnings.push(translateNow("session.memoryUpdateError"));
    }
    return warnings.join(" ");
  }

  /** @param {string} reason */
  function abortPendingTurn(reason = "user") {
    if (!turnAbortController) {
      return;
    }
    turnAbortController.abort(reason);
  }

  function stopGeneration() {
    abortPendingTurn("user");
  }

  /** @param {unknown} caught */
  function isAbortError(caught) {
    return caught instanceof DOMException && caught.name === "AbortError";
  }

  /** @param {Record<string, any>} message */
  /**
   * @param {string} scenarioId
   * @param {string} sessionId
   * @param {Record<string, any>} message
   */
  async function handleRegenerate(scenarioId, sessionId, message) {
    if (!scenarioId || !sessionId || !message || message.turn == null || sending) return;
    const doRegenerate = window.confirm(translateNow("session.regenerateConfirm", { turn: message.turn }));
    if (!doRegenerate) return;

    sending = true;
    error = "";
    turnNotice = "";

    turnAbortController = new AbortController();

    try {
      if (get(deps.preferences).streamEnabled) {
        let streamContent = "";

        await regenerateTurnStream(scenarioId, sessionId, message.turn, {
          signal: turnAbortController.signal,
          onDelta: (delta) => {
            streamContent += delta;
            messages = updateRegeneratingAssistantMessage(messages, message.turn, streamContent);
            tick().then(deps.scrollToBottom);
          }
        });
      } else {
        await regenerateTurn(scenarioId, sessionId, message.turn, {
          signal: turnAbortController.signal
        });
      }
    } catch (err) {
      if (!isAbortError(err)) {
        error = err instanceof Error ? err.message : translateNow("session.regenerateError");
      } else {
        turnNotice = translateNow("session.regenerateAborted");
      }
    } finally {
      sending = false;
      turnAbortController = null;
      await deps.reloadSession(scenarioId, sessionId, { timeline: true });
      if (!get(deps.preferences).streamEnabled) {
        newMessageBadge = true;
      }
    }
  }

  /** @param {Record<string, any>} message */
  /**
   * @param {string} scenarioId
   * @param {string} sessionId
   * @param {Record<string, any>} message
   */
  async function handleContinue(scenarioId, sessionId, message) {
    if (!scenarioId || !sessionId || !message || message.turn == null || sending) return;

    sending = true;
    error = "";
    turnNotice = "";

    turnAbortController = new AbortController();

    try {
      if (get(deps.preferences).streamEnabled) {
        let appendedContent = "";

        await continueTurnStream(scenarioId, sessionId, message.turn, {
          signal: turnAbortController.signal,
          onDelta: (delta) => {
            appendedContent += delta;
            messages = updateStreamingContinuedAssistantMessage(messages, message.turn, appendedContent);
            tick().then(deps.scrollToBottom);
          }
        });
      } else {
        await continueTurn(scenarioId, sessionId, message.turn, {
          signal: turnAbortController.signal
        });
      }
    } catch (err) {
      if (!isAbortError(err)) {
        error = err instanceof Error ? err.message : translateNow("session.continueError");
      } else {
        turnNotice = translateNow("session.continueAborted");
      }
    } finally {
      sending = false;
      turnAbortController = null;
      await deps.reloadSession(scenarioId, sessionId, { timeline: true });
      if (!get(deps.preferences).streamEnabled) {
        newMessageBadge = true;
      }
    }
  }

  function dispose() {
    abortPendingTurn("destroy");
    clearTurnPollTimer();
    clearPostprocessPollTimer();
  }

  return {
    get messages() { return messages; },
    set messages(value) { messages = value; },
    get sending() { return sending; },
    set sending(value) { sending = value; },
    get stateUpdating() { return stateUpdating; },
    set stateUpdating(value) { stateUpdating = value; },
    get turnJobPolling() { return turnJobPolling; },
    get turnNotice() { return turnNotice; },
    set turnNotice(value) { turnNotice = value; },
    get error() { return error; },
    set error(value) { error = value; },
    get input() { return input; },
    set input(value) { input = value; },
    get newMessageBadge() { return newMessageBadge; },
    set newMessageBadge(value) { newMessageBadge = value; },
    submitTurn,
    resumePendingJobs,
    handleRegenerate,
    handleContinue,
    stopGeneration,
    abortPendingTurn,
    dispose
  };
}

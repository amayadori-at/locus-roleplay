<script>
  import {
    ArrowLeft,
    Asterisk,
    Braces,
    ChevronDown,
    ChevronLeft,
    ChevronRight,
    FileStack,
    ImageOff,
    Info,
    Pencil,
    PanelLeftClose,
    PanelLeftOpen,
    PanelRightOpen,
    RefreshCcw,
    Send,
    Settings,
    Square,
    Trash2,
    Wand2
  } from "lucide-svelte";
  import { onDestroy, onMount, tick } from "svelte";
  import {
    createBranchSession,
    createSession,
    getScenarioRagStatus,
    getScenarioState,
    getPostprocessJob,
    getSessionDetail,
    getSessionLog,
    getSessionPromptPreview,
    getSessionTimeline,
    getTurnJob,
    listPersonas,
    listProfiles,
    listScenarioMemory,
    listScenarioCharacterBustups,
    listScenarioStartings,
    rebuildScenarioRagIndex,
    sendTurn,
    sendTurnStream,
    updateSessionSettings,
    updateSessionMessage,
    deleteSessionMessage,
    switchAssistantCandidate,
    regenerateTurn,
    regenerateTurnStream,
    continueTurn,
    continueTurnStream,
    getSessionPins,
    updateSessionPins,
    updateSessionStarting,
    updateMemoryMetadata
  } from "../lib/api.js";
  import {
    EMPTY_SELECTION,
    createSessionSelectionStore,
    personaName,
    profileModel
  } from "../lib/sessionSelection.js";
  import { createSessionLayoutStore } from "../lib/sessionLayout.js";
  import { shouldSubmitComposer, wrapComposerSelection } from "../lib/sessionComposer.js";
  import {
    appendPendingTurnMessages,
    appendStreamingDeltaToMessages,
    finalizeTurnMessages,
    formatResponseDuration,
    mergeLogPagination,
    mergeOlderLogMessages,
    nextAssistantCandidateIndex,
    removePendingTurnMessages,
    updateRegeneratingAssistantMessage,
    updateStreamingContinuedAssistantMessage
  } from "../lib/sessionLog.js";
  import { createSessionPickerStore } from "../lib/sessionPicker.js";
  import { createSessionPreferencesStore } from "../lib/sessionPreferences.js";
  import { displayMessageSegments } from "../lib/messageSegments.js";
  import { t, translateNow } from "../lib/i18n.js";
  import { renderMarkdown } from "../lib/markdown.js";
  import PersonaProfilePickerModal from "../lib/PersonaProfilePickerModal.svelte";
  import TimelinePanel from "../lib/TimelinePanel.svelte";
  import StatePanel from "../lib/StatePanel.svelte";
  import SessionSettingsModal from "../lib/SessionSettingsModal.svelte";

  /**
   * @typedef {{
   *   scenarioId?: string,
   *   sessionId?: string
   * }} SessionRoute
   *
   */

  /** @type {SessionRoute} */
  export let route;
  /**
   * @type {{
   *   openHome: () => void,
   *   openSession: (scenarioId: string, sessionId?: string) => void,
   *   openScenarioEdit?: (scenarioId: string, sourcePath?: string) => void
   * }}
   */
  export let onNavigate = {
    openHome: () => {},
    openSession: () => {},
    openScenarioEdit: () => {}
  };

  const LOG_TURN_PAGE_SIZE = 10;

  $: userLabel = ($selection.selectedPersona && $selection.selectedPersona !== EMPTY_SELECTION)
    ? personaName($selection, $selection.selectedPersona)
    : "User";

  /** @param {string} content */
  function resolveUser(content) {
    if (!content.includes("{{user}}")) return content;
    return content.replaceAll("{{user}}", userLabel);
  }

  /** @type {Array<{ role: string, content: string, segments?: Array<Record<string, any>>, turn?: number, streaming?: boolean, candidates?: string[], active_candidate_index?: number, is_starting?: boolean, starting_id?: string, response_duration_ms?: number }>} */
  let messages = [];
  /** @type {Array<Record<string, any>>} */
  let timeline = [];
  /** @type {Record<string, any>} */
  let timelineMetadata = {};
  /** @type {Record<string, any> | null} */
  let state = null;
  let currentSessionId = "";
  let loading = false;
  let loadingOlderLog = false;
  let sending = false;
  let stateUpdating = false;
  let turnJobPolling = false;
  let error = "";
  let turnNotice = "";
  let input = "";
  let isMobile = false;
  let activeAssistantCandidate = 1;
  let assistantCandidateCount = 1;
  /** @type {Record<string, boolean>} */
  let expandedMetaSegments = {};
  /** @type {Record<string, any>} */
  let sessionMetadata = {};
  /** @type {Record<string, any>} */
  let logPagination = {};
  /** @type {"info" | "settings" | ""} */
  let sessionModal = "";
  let sessionNoteDraft = "";
  let sceneNoteDraft = "";
  let settingsSaving = false;
  let settingsMessage = "";
  /** @type {Record<string, any> | null} */
  let pinsData = null;
  let pinsLoading = false;
  let pinsSaving = false;
  let pinsMessage = "";
  /** @type {number | null} */
  let editMessageTurn = null;
  let editMessageRole = "";
  let editDraft = "";
  let editSaving = false;
  /** @type {number | null} */
  let branchTurnDraft = null;
  let branchNameDraft = "";
  let branchSaving = false;
  let branchError = "";
  /** @type {number | null} */
  let deletingTurn = null;
  let deletingRole = "";
  let promptPreviewLoading = false;
  let promptPreviewError = "";
  /** @type {Record<string, any> | null} */
  let promptPreview = null;
  let ragStatusLoading = false;
  let ragStatusError = "";
  /** @type {Record<string, any> | null} */
  let ragStatus = null;
  let memoryLoading = false;
  let memoryError = "";
  /** @type {Record<string, any> | null} */
  let memoryList = null;
  let memoryStatusSaving = false;
  let memoryStatusMessage = "";
  let activeMemoryPath = "";
  /** @type {Record<string, any> | null} */
  let selectedMemoryItem = null;
  let ragRebuildRunning = false;
  let ragRebuildMessage = "";
  /** @type {Array<Record<string, any>>} */
  let startings = [];
  /** @type {Array<Record<string, any>>} */
  let characterBustups = [];
  let selectedStartingId = "";
  let switchingStarting = false;
  let newMessageBadge = false;
  let loadedKey = "";
  let currentRouteKey = "";
  let showSessionSide = true;
  const selection = createSessionSelectionStore();
  const layout = createSessionLayoutStore();
  const pickerState = createSessionPickerStore();
  const preferences = createSessionPreferencesStore();
  const BRANCH_EDIT_PRESET_PREFIX = "locus-rp:branch-edit-preset:";
  /** @type {HTMLTextAreaElement | null} */
  let composer = null;
  /** @type {HTMLElement | null} */
  let chatLogElement = null;
  /** @type {AbortController | null} */
  let turnAbortController = null;
  /** @type {ReturnType<typeof setTimeout> | null} */
  let postprocessPollTimer = null;
  /** @type {ReturnType<typeof setTimeout> | null} */
  let turnPollTimer = null;

  $: selectedMemoryItem = activeMemoryItem();
  $: showSessionSide = !isMobile || Boolean(currentSessionId);
  $: if (!showSessionSide && $layout.sideOpen) layout.setSideOpen(false);

  onMount(() => {
    const query = window.matchMedia("(max-width: 860px)");
    const applyViewportMode = () => {
      isMobile = query.matches;
      layout.applyViewportMode(isMobile);
    };
    applyViewportMode();
    query.addEventListener("change", applyViewportMode);
    return () => query.removeEventListener("change", applyViewportMode);
  });

  async function scrollToBottom() {
    await tick();
    if (chatLogElement) {
      chatLogElement.scrollTop = chatLogElement.scrollHeight;
    }
  }

  async function dismissNewMessageBadge() {
    newMessageBadge = false;
    await scrollToBottom();
  }

  function handleChatLogScroll() {
    if (!chatLogElement) return;
    const { scrollTop, scrollHeight, clientHeight } = chatLogElement;
    if (scrollHeight - scrollTop - clientHeight < 40) {
      newMessageBadge = false;
    }
    if (scrollTop < 120 && logPagination.has_more_before && !loadingOlderLog && !sending) {
      void loadOlderLog();
    }
  }

  /**
   * @param {number} targetTurn
   */
  async function loadAroundTurn(targetTurn) {
    if (!route.scenarioId || !currentSessionId) return;
    loadingOlderLog = true;
    const fromTurn = Math.max(0, targetTurn - Math.floor(LOG_TURN_PAGE_SIZE / 2));
    try {
      const payload = await getSessionLog(route.scenarioId, currentSessionId, {
        turnLimit: LOG_TURN_PAGE_SIZE,
        fromTurn
      });
      messages = payload.log || [];
      logPagination = payload.pagination || {};
    } catch (caught) {
      error = caught instanceof Error ? caught.message : translateNow("session.loadLogError");
    } finally {
      loadingOlderLog = false;
    }
  }

  async function loadLatestLog() {
    if (!route.scenarioId || !currentSessionId) return;
    await loadLog(route.scenarioId, currentSessionId);
    await scrollToBottom();
  }

  /**
   * @param {number} turn
   * @param {string} role
   */
  async function handleJumpToTurn(turn, role) {
    const id = `message-turn-${turn}-${role}`;
    let el = document.getElementById(id);
    if (!el) {
      await loadAroundTurn(turn);
      await tick();
      el = document.getElementById(id);
    }
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.add("highlight-message");
      setTimeout(() => el.classList.remove("highlight-message"), 2000);
    }
  }

  /** @param {number} turn */
  function openBranchDialog(turn) {
    if (!route.scenarioId || !currentSessionId || sending) {
      return;
    }
    branchTurnDraft = turn;
    branchNameDraft = defaultBranchName(turn);
    branchError = branchSnapshotAvailable(turn)
      ? ""
      : translateNow("session.noSnapshot");
  }

  function closeBranchDialog() {
    if (branchSaving) return;
    branchTurnDraft = null;
    branchNameDraft = "";
    branchError = "";
  }

  /** @param {number} turn */
  function defaultBranchName(turn) {
    return translateNow("session.branchName", { name: sessionMetadata.display_name || currentSessionId, turn });
  }

  /** @param {number} turn */
  function branchSnapshotAvailable(turn) {
    const item = timeline.find((entry) => entry.turn === turn);
    return item?.state_snapshot_available === true;
  }

  /** @param {number} turn */
  async function handleBranchFromTurn(turn) {
    if (!route.scenarioId || !currentSessionId || sending) {
      return;
    }
    const displayName = branchNameDraft.trim() || defaultBranchName(turn);
    branchSaving = true;
    branchError = "";
    error = "";
    try {
      const payload = await createBranchSession(route.scenarioId, currentSessionId, {
        branched_from_turn: turn,
        display_name: displayName
      });
      const sessionId = payload.session?.session_id;
      if (!sessionId) {
        throw new Error(translateNow("session.backendBranchError"));
      }
      if (payload.session?.state_snapshot_available === false) {
        turnNotice = translateNow("session.branchStateFallback");
      }
      branchTurnDraft = null;
      branchNameDraft = "";
      onNavigate.openSession(route.scenarioId, sessionId);
    } catch (caught) {
      branchError = caught instanceof Error ? caught.message : translateNow("session.branchCreateError");
    } finally {
      branchSaving = false;
    }
  }

  /**
   * @param {number} turn
   * @param {boolean} bookmarked
   */
  async function handleToggleBookmark(turn, bookmarked) {
    if (!route.scenarioId || !currentSessionId || sending) {
      return;
    }
    const current = Array.isArray(sessionMetadata.bookmarked_turns) ? sessionMetadata.bookmarked_turns : [];
    const next = bookmarked
      ? Array.from(new Set([...current, turn])).sort((left, right) => left - right)
      : current.filter((item) => item !== turn);
    sessionMetadata = { ...sessionMetadata, bookmarked_turns: next };
    timeline = timeline.map((item) => (item.turn === turn ? { ...item, bookmarked } : item));
    try {
      const payload = await updateSessionSettings(route.scenarioId, currentSessionId, { bookmarked_turns: next });
      sessionMetadata = payload.session || sessionMetadata;
      await loadTimeline(route.scenarioId, currentSessionId);
    } catch (caught) {
      error = caught instanceof Error ? caught.message : translateNow("session.bookmarkSaveError");
      await loadTimeline(route.scenarioId, currentSessionId);
    }
  }

  /** @param {string} id */
  async function handleSessionRpProfileChange(id) {
    if (!route.scenarioId || !currentSessionId) return;
    if (!id || id === EMPTY_SELECTION) return;
    if (id === sessionMetadata.rp_profile_id) return;
    try {
      const payload = await updateSessionSettings(route.scenarioId, currentSessionId, { rp_profile_id: id });
      sessionMetadata = payload.session || sessionMetadata;
    } catch (caught) {
      error = caught instanceof Error ? caught.message : translateNow("session.profileUpdateError");
    }
  }

  /** @param {string} id */
  async function handleSessionStateProfileChange(id) {
    if (!route.scenarioId || !currentSessionId) return;
    if (!id || id === EMPTY_SELECTION) return;
    if (id === sessionMetadata.summary_profile_id) return;
    try {
      const payload = await updateSessionSettings(route.scenarioId, currentSessionId, { summary_profile_id: id });
      sessionMetadata = payload.session || sessionMetadata;
    } catch (caught) {
      error = caught instanceof Error ? caught.message : translateNow("session.profileUpdateError");
    }
  }

  $: currentRouteKey = `${route.scenarioId || ""}:${route.sessionId || ""}`;
  $: if (currentRouteKey && currentRouteKey !== loadedKey) {
    void initialize(currentRouteKey);
  }

  /** @param {string} routeKey */
  async function initialize(routeKey) {
    abortPendingTurn("route_change");
    loadedKey = routeKey;
    error = "";
    turnNotice = "";
    messages = [];
    logPagination = {};
    timeline = [];
    timelineMetadata = {};
    state = null;
    sessionMetadata = {};
    sessionModal = "";
    settingsMessage = "";
    promptPreviewError = "";
    promptPreview = null;
    ragStatusError = "";
    ragStatus = null;
    memoryError = "";
    memoryList = null;
    activeMemoryPath = "";
    ragRebuildMessage = "";
    startings = [];
    characterBustups = [];
    selectedStartingId = "";
    switchingStarting = false;
    currentSessionId = route.sessionId || "";

    if (!route.scenarioId) {
      error = translateNow("session.noScenario");
      return;
    }

    loading = true;
    try {
      if (!currentSessionId) {
        await loadChoices();
        selection.applyDefaults();
        return;
      }
      await Promise.all([
        loadChoices(),
        loadLog(route.scenarioId, currentSessionId),
        loadTimeline(route.scenarioId, currentSessionId),
        loadState(route.scenarioId, currentSessionId)
      ]);
      await resumePendingJobs(route.scenarioId, currentSessionId);
      applyBranchEditPreset(route.scenarioId, currentSessionId);
    } catch (caught) {
      error = caught instanceof Error ? caught.message : translateNow("session.loadSessionError");
    } finally {
      loading = false;
      if (currentSessionId && (sessionMetadata.turn_count ?? 0) > 0) {
        await scrollToBottom();
      }
    }
  }

  async function loadChoices() {
    const [personaPayload, profilePayload, startingPayload, bustupPayload] = await Promise.all([
      listPersonas(),
      listProfiles(),
      route.scenarioId ? listScenarioStartings(route.scenarioId) : Promise.resolve({ startings: [] }),
      route.scenarioId ? listScenarioCharacterBustups(route.scenarioId) : Promise.resolve({ characters: [] })
    ]);
    selection.setChoices(personaPayload.personas || [], profilePayload.profiles || []);
    startings = startingPayload.startings || [];
    characterBustups = bustupPayload.characters || [];
    selectedStartingId = startings[0]?.id || "";
  }

  async function createSelectedSession() {
    if (!route.scenarioId) {
      error = translateNow("session.noScenario");
      return;
    }
    if (!$selection.selectedPersona || $selection.selectedPersona === EMPTY_SELECTION) {
      error = translateNow("session.noPersona");
      return;
    }
    if (!$selection.selectedRpProfile || $selection.selectedRpProfile === EMPTY_SELECTION) {
      error = translateNow("session.noProfile");
      return;
    }

    loading = true;
    error = "";
    try {
      const payload = await createSession({
        scenario_id: route.scenarioId,
        persona_id: $selection.selectedPersona,
        rp_profile_id: $selection.selectedRpProfile,
        summary_profile_id: $selection.selectedStateProfile === EMPTY_SELECTION ? null : $selection.selectedStateProfile,
        starting_id: selectedStartingId || null
      });
      const sessionId = payload.session?.session_id;
      if (!sessionId) {
        throw new Error(translateNow("session.backendSessionError"));
      }
      onNavigate.openSession(route.scenarioId, sessionId);
    } catch (caught) {
      error = caught instanceof Error ? caught.message : translateNow("session.createSessionError");
    } finally {
      loading = false;
    }
  }

  /**
   * @param {string} scenarioId
   * @param {string} sessionId
   */
  async function loadLog(scenarioId, sessionId) {
    const payload = await getSessionLog(scenarioId, sessionId, { turnLimit: LOG_TURN_PAGE_SIZE });
    messages = payload.log || [];
    logPagination = payload.pagination || {};
    sessionMetadata = payload.metadata || {};
    sessionNoteDraft = metadataSessionNote(sessionMetadata);
    sceneNoteDraft = typeof sessionMetadata.scene_note === "string" ? sessionMetadata.scene_note : "";
    selection.applyMetadata(payload.metadata || {});
  }

  async function loadOlderLog() {
    if (!route.scenarioId || !currentSessionId || loadingOlderLog || sending || !logPagination.has_more_before) {
      return;
    }
    loadingOlderLog = true;
    error = "";
    const previousHeight = chatLogElement?.scrollHeight || 0;
    try {
      const payload = await getSessionLog(route.scenarioId, currentSessionId, {
        turnLimit: LOG_TURN_PAGE_SIZE,
        beforeTurn: logPagination.min_turn
      });
      messages = mergeOlderLogMessages(messages, payload.log || []);
      logPagination = mergeLogPagination(logPagination, payload.pagination || {});
      await tick();
      if (chatLogElement) {
        chatLogElement.scrollTop = chatLogElement.scrollHeight - previousHeight;
      }
    } catch (caught) {
      error = caught instanceof Error ? caught.message : translateNow("session.loadOlderError");
    } finally {
      loadingOlderLog = false;
    }
  }

  /**
   * @param {string} scenarioId
   * @param {string} sessionId
   */
  async function loadTimeline(scenarioId, sessionId) {
    const payload = await getSessionTimeline(scenarioId, sessionId);
    timeline = payload.timeline || [];
    timelineMetadata = payload.metadata || {};
  }

  /**
   * @param {string} scenarioId
   * @param {string} [sessionId]
   */
  async function loadState(scenarioId, sessionId = currentSessionId) {
    const payload = await getScenarioState(scenarioId, sessionId);
    state = payload.state || {};
  }

  /**
   * @param {string} scenarioId
   * @param {string} sessionId
   * @param {{ log?: boolean, state?: boolean, timeline?: boolean }} [opts]
   */
  async function reloadSession(scenarioId, sessionId, opts = {}) {
    const { log: doLog = true, state: doState = true, timeline: doTimeline = false } = opts;
    const tasks = [];
    if (doLog) tasks.push(loadLog(scenarioId, sessionId));
    if (doState) tasks.push(loadState(scenarioId, sessionId));
    if (doTimeline) tasks.push(loadTimeline(scenarioId, sessionId));
    await Promise.all(tasks);
  }

  async function submitTurn() {
    const userMessage = input.trim();
    if (!route.scenarioId || !currentSessionId || !userMessage || sending || stateUpdating) {
      return;
    }

    const scenarioId = route.scenarioId;
    const sessionId = currentSessionId;
    const controller = new AbortController();
    turnAbortController = controller;
    input = "";
    error = "";
    turnNotice = "";
    newMessageBadge = false;
    sending = true;
    turnJobPolling = false;
    const useStream = $preferences.streamEnabled;
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
            void loadTimeline(scenarioId, sessionId);
            if (sessionModal === "settings") {
              void Promise.all([loadPromptPreview(scenarioId, sessionId), loadRagStatus(scenarioId)]);
            }
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
            await loadLog(scenarioId, sessionId);
          }
          await loadTimeline(scenarioId, sessionId);
          if (postprocessJob && typeof postprocessJob.job_id === "string") {
            stateUpdating = true;
            await handlePostTurnResult(scenarioId, sessionId, { postprocess_job: postprocessJob });
          } else {
            turnNotice = formatPostTurnNotice(turn);
            await loadState(scenarioId, sessionId);
          }
          if (sessionModal === "settings") {
            await Promise.all([loadPromptPreview(scenarioId, sessionId), loadRagStatus(scenarioId)]);
          }
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
    await Promise.all([loadState(scenarioId, sessionId), loadTimeline(scenarioId, sessionId)]);
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
          await Promise.all([loadState(scenarioId, sessionId), loadTimeline(scenarioId, sessionId)]);
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

  onDestroy(() => {
    abortPendingTurn("destroy");
    clearTurnPollTimer();
    clearPostprocessPollTimer();
  });

  /** @param {Record<string, any>} message */
  function startEditing(message) {
    if (!message || message.turn == null) return;
    editMessageTurn = message.turn;
    editMessageRole = message.role;
    editDraft = message.content || "";
  }

  function cancelEditing() {
    editMessageTurn = null;
    editMessageRole = "";
    editDraft = "";
  }

  $: latestTurn = messages.length
    ? Math.max(...messages.filter((m) => m.turn != null).map((m) => /** @type {number} */ (m.turn)))
    : -1;

  /** @param {Record<string, any>} message */
  async function saveEdit(message) {
    if (!route.scenarioId || !currentSessionId || editSaving) return;
    editSaving = true;
    try {
      if (shouldBranchFromEditedUserMessage(message)) {
        const turn = /** @type {number} */ (message.turn);
        const payload = await createBranchSession(route.scenarioId, currentSessionId, {
          branched_from_turn: turn - 1,
          display_name: translateNow("session.editBranchName", { name: sessionMetadata.display_name || currentSessionId, turn })
        });
        const sessionId = payload.session?.session_id;
        if (!sessionId) {
          throw new Error(translateNow("session.backendBranchError"));
        }
        setBranchEditPreset(route.scenarioId, sessionId, editDraft.trim());
        cancelEditing();
        onNavigate.openSession(route.scenarioId, sessionId);
        return;
      }
      await updateSessionMessage(route.scenarioId, currentSessionId, message.turn, message.role, editDraft);
      editMessageTurn = null;
      editMessageRole = "";
      await reloadSession(route.scenarioId, currentSessionId);
    } catch (err) {
      alert(translateNow("session.editSaveError", { message: err instanceof Error ? err.message : String(err) }));
    } finally {
      editSaving = false;
    }
  }

  /** @param {Record<string, any>} message */
  function shouldBranchFromEditedUserMessage(message) {
    return message?.role === "user" && Number.isInteger(message.turn) && message.turn >= 1;
  }

  /**
   * @param {string} scenarioId
   * @param {string} sessionId
   * @param {string} content
   */
  function setBranchEditPreset(scenarioId, sessionId, content) {
    if (!content) return;
    sessionStorage.setItem(`${BRANCH_EDIT_PRESET_PREFIX}${scenarioId}:${sessionId}`, content);
  }

  /**
   * @param {string} scenarioId
   * @param {string} sessionId
   */
  function applyBranchEditPreset(scenarioId, sessionId) {
    const key = `${BRANCH_EDIT_PRESET_PREFIX}${scenarioId}:${sessionId}`;
    const preset = sessionStorage.getItem(key);
    if (!preset) return;
    sessionStorage.removeItem(key);
    input = preset;
    turnNotice = translateNow("session.editBranchNotice");
    tick().then(() => composer?.focus());
  }

  /** @param {Record<string, any>} message */
  async function handleDeleteMessage(message) {
    if (!route.scenarioId || !currentSessionId || !message || message.turn == null) return;
    const doDelete = window.confirm(translateNow("session.deleteConfirm", { turn: message.turn, role: message.role === "assistant" ? translateNow("session.gmResponse") : translateNow("session.userMessage") }));
    if (!doDelete) return;

    const doRewind = window.confirm(translateNow("session.deleteRewindConfirm"));

    deletingTurn = message.turn;
    deletingRole = message.role;
    try {
      await deleteSessionMessage(route.scenarioId, currentSessionId, message.turn, message.role, doRewind);
      await reloadSession(route.scenarioId, currentSessionId, { timeline: true });
    } catch (err) {
      alert(translateNow("session.deleteError", { message: err instanceof Error ? err.message : String(err) }));
    } finally {
      deletingTurn = null;
      deletingRole = "";
    }
  }

  /**
   * @param {Record<string, any>} message
   * @param {"prev" | "next"} direction
   */
  async function handleSwitchCandidate(message, direction) {
    if (!route.scenarioId || !currentSessionId || !message || message.turn == null) return;
    const activeIndex = nextAssistantCandidateIndex(message, direction);
    if (activeIndex == null) return;

    try {
      await switchAssistantCandidate(route.scenarioId, currentSessionId, message.turn, activeIndex);
      await loadLog(route.scenarioId, currentSessionId);
    } catch (err) {
      alert(translateNow("session.switchError", { message: err instanceof Error ? err.message : String(err) }));
    }
  }

  /** @param {Record<string, any>} message */
  async function handleRegenerate(message) {
    if (!route.scenarioId || !currentSessionId || !message || message.turn == null || sending) return;
    const doRegenerate = window.confirm(translateNow("session.regenerateConfirm", { turn: message.turn }));
    if (!doRegenerate) return;

    sending = true;
    error = "";
    turnNotice = "";

    turnAbortController = new AbortController();

    try {
      if ($preferences.streamEnabled) {
        let streamContent = "";

        await regenerateTurnStream(route.scenarioId, currentSessionId, message.turn, {
          signal: turnAbortController.signal,
          onDelta: (delta) => {
            streamContent += delta;
            messages = updateRegeneratingAssistantMessage(messages, message.turn, streamContent);
            tick().then(scrollToBottom);
          }
        });
      } else {
        await regenerateTurn(route.scenarioId, currentSessionId, message.turn, {
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
      await reloadSession(route.scenarioId, currentSessionId, { timeline: true });
      if (!$preferences.streamEnabled) {
        newMessageBadge = true;
      }
    }
  }

  /** @param {Record<string, any>} message */
  async function handleContinue(message) {
    if (!route.scenarioId || !currentSessionId || !message || message.turn == null || sending) return;

    sending = true;
    error = "";
    turnNotice = "";

    turnAbortController = new AbortController();

    try {
      if ($preferences.streamEnabled) {
        let appendedContent = "";

        await continueTurnStream(route.scenarioId, currentSessionId, message.turn, {
          signal: turnAbortController.signal,
          onDelta: (delta) => {
            appendedContent += delta;
            messages = updateStreamingContinuedAssistantMessage(messages, message.turn, appendedContent);
            tick().then(scrollToBottom);
          }
        });
      } else {
        await continueTurn(route.scenarioId, currentSessionId, message.turn, {
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
      await reloadSession(route.scenarioId, currentSessionId, { timeline: true });
      if (!$preferences.streamEnabled) {
        newMessageBadge = true;
      }
    }
  }

  /** @param {'quote' | 'asterisk'} mode */
  async function wrapSelection(mode) {
    if (!composer) {
      return;
    }
    const start = composer.selectionStart;
    const end = composer.selectionEnd;
    const wrapped = wrapComposerSelection(input, start, end, mode);
    input = wrapped.value;
    await tick();
    composer.focus();
    composer.setSelectionRange(wrapped.cursor, wrapped.cursor);
  }

  /** @param {KeyboardEvent} event */
  function handleKeydown(event) {
    if (sending || !currentSessionId) return;
    if (!shouldSubmitComposer(event, $preferences.sendOnEnter)) return;
    event.preventDefault();
    if (input.trim()) void submitTurn();
  }

  function adjustTextareaHeight() {
    if (composer) {
      composer.style.height = "auto";
      composer.style.height = Math.max(48, composer.scrollHeight) + "px";
    }
  }

  $: if (input !== undefined) {
    tick().then(adjustTextareaHeight);
  }

  /** @param {{ role: string, content: string, segments?: Array<Record<string, any>>, streaming?: boolean }} message */
  function displaySegments(message) {
    return displayMessageSegments(message, characterBustups);
  }

  /**
   * @param {{ role: string, turn?: number }} message
   * @param {number} index
   */
  function metaSegmentKey(message, index) {
    return `${message.turn ?? "draft"}:${message.role}:${index}`;
  }

  /** @param {string} key */
  function toggleMetaSegment(key) {
    expandedMetaSegments = {
      ...expandedMetaSegments,
      [key]: expandedMetaSegments[key] === true ? false : true,
    };
  }

  function stateJson() {
    return JSON.stringify(state || {}, null, 2);
  }

  /** @param {Record<string, any> | null | undefined} metadata */
  function metadataSessionNote(metadata) {
    if (typeof metadata?.session_note === "string") return metadata.session_note;
    if (typeof metadata?.user_note === "string") return metadata.user_note;
    return "";
  }

  function openSessionInfo() {
    sessionModal = "info";
    settingsMessage = "";
  }

  function openSessionSettings() {
    sessionNoteDraft = metadataSessionNote(sessionMetadata);
    sceneNoteDraft = typeof sessionMetadata.scene_note === "string" ? sessionMetadata.scene_note : "";
    sessionModal = "settings";
    settingsMessage = "";
    if (route.scenarioId && currentSessionId) {
      void loadPromptPreview(route.scenarioId, currentSessionId);
      void loadRagStatus(route.scenarioId);
      void loadMemoryList(route.scenarioId, currentSessionId);
      void loadPins(route.scenarioId, currentSessionId);
    }
  }

  async function loadPins(/** @type {string} */ scenarioId, /** @type {string} */ sessionId) {
    pinsLoading = true;
    pinsMessage = "";
    try {
      pinsData = await getSessionPins(scenarioId, sessionId);
    } catch {
      pinsData = null;
    } finally {
      pinsLoading = false;
    }
  }

  async function toggleMod(/** @type {string} */ path) {
    if (!route.scenarioId || !currentSessionId || pinsSaving || !pinsData) return;
    const current = Array.isArray(pinsData.active_mods) ? pinsData.active_mods : [];
    const next = current.includes(path) ? current.filter((/** @type {string} */ p) => p !== path) : [...current, path];
    pinsSaving = true;
    pinsMessage = "";
    try {
      const result = await updateSessionPins(route.scenarioId, currentSessionId, { active_mods: next });
      pinsData = result;
      sessionMetadata = { ...sessionMetadata, active_mods: result.active_mods };
    } catch (caught) {
      pinsMessage = caught instanceof Error ? caught.message : translateNow("session.saveError");
    } finally {
      pinsSaving = false;
    }
  }

  async function togglePinnedCharacter(/** @type {string} */ path) {
    if (!route.scenarioId || !currentSessionId || pinsSaving || !pinsData) return;
    const current = Array.isArray(pinsData.pinned_characters) ? pinsData.pinned_characters : [];
    const next = current.includes(path) ? current.filter((/** @type {string} */ p) => p !== path) : [...current, path];
    pinsSaving = true;
    pinsMessage = "";
    try {
      const result = await updateSessionPins(route.scenarioId, currentSessionId, { pinned_characters: next });
      pinsData = result;
      sessionMetadata = { ...sessionMetadata, pinned_characters: result.pinned_characters };
    } catch (caught) {
      pinsMessage = caught instanceof Error ? caught.message : translateNow("session.saveError");
    } finally {
      pinsSaving = false;
    }
  }

  function closeSessionModal() {
    sessionModal = "";
    settingsMessage = "";
  }

  async function saveSessionSettings() {
    if (!route.scenarioId || !currentSessionId || settingsSaving) {
      return;
    }
    settingsSaving = true;
    settingsMessage = "";
    try {
      const payload = await updateSessionSettings(route.scenarioId, currentSessionId, {
        session_note: sessionNoteDraft,
        scene_note: sceneNoteDraft
      });
      sessionMetadata = payload.session || {};
      sessionNoteDraft = metadataSessionNote(sessionMetadata);
      sceneNoteDraft = typeof sessionMetadata.scene_note === "string" ? sessionMetadata.scene_note : "";
      settingsMessage = translateNow("session.saved");
    } catch (caught) {
      settingsMessage = caught instanceof Error ? caught.message : translateNow("session.settingsSaveError");
    } finally {
      settingsSaving = false;
    }
  }

  /**
   * @param {string} scenarioId
   * @param {string} sessionId
   */
  async function loadPromptPreview(scenarioId, sessionId) {
    promptPreviewLoading = true;
    promptPreviewError = "";
    try {
      promptPreview = await getSessionPromptPreview(scenarioId, sessionId);
    } catch (caught) {
      promptPreviewError = caught instanceof Error ? caught.message : translateNow("session.promptPreviewError");
      promptPreview = null;
    } finally {
      promptPreviewLoading = false;
    }
  }

  /** @param {string} scenarioId */
  async function loadRagStatus(scenarioId) {
    ragStatusLoading = true;
    ragStatusError = "";
    try {
      ragStatus = await getScenarioRagStatus(scenarioId);
    } catch (caught) {
      ragStatusError = caught instanceof Error ? caught.message : translateNow("session.ragStatusError");
      ragStatus = null;
    } finally {
      ragStatusLoading = false;
    }
  }

  /**
   * @param {string} scenarioId
   * @param {string} sessionId
   */
  async function loadMemoryList(scenarioId, sessionId, preferredPath = "") {
    memoryLoading = true;
    memoryError = "";
    try {
      memoryList = await listScenarioMemory(scenarioId, sessionId);
      activeMemoryPath = findMemoryItem(preferredPath)?.path || firstMemoryItem()?.path || "";
    } catch (caught) {
      memoryError = caught instanceof Error ? caught.message : translateNow("session.memoryListError");
      memoryList = null;
      activeMemoryPath = "";
    } finally {
      memoryLoading = false;
    }
  }

  async function rebuildRagIndex() {
    if (!route.scenarioId || ragRebuildRunning) {
      return;
    }
    ragRebuildRunning = true;
    ragRebuildMessage = "";
    ragStatusError = "";
    try {
      const payload = await rebuildScenarioRagIndex(route.scenarioId);
      ragRebuildMessage = translateNow("session.ragRebuildDone", { count: payload.index?.document_count ?? 0 });
      await loadRagStatus(route.scenarioId);
      if (currentSessionId) {
        await loadMemoryList(route.scenarioId, currentSessionId);
      }
    } catch (caught) {
      ragStatusError = caught instanceof Error ? caught.message : translateNow("session.ragRebuildError");
    } finally {
      ragRebuildRunning = false;
    }
  }

  function memoryGroups() {
    return memoryList?.groups || {};
  }

  function firstMemoryItem() {
    const groups = memoryGroups();
    for (const key of ["session_summaries", "extracted_facts", "unresolved_threads"]) {
      const items = groups[key];
      if (Array.isArray(items) && items.length) {
        return items[0];
      }
    }
    return null;
  }

  /** @param {string} path */
  function findMemoryItem(path) {
    if (!path) return null;
    const groups = memoryGroups();
    for (const items of Object.values(groups)) {
      if (!Array.isArray(items)) continue;
      const found = items.find((item) => item.path === path);
      if (found) return found;
    }
    return null;
  }

  function activeMemoryItem() {
    return findMemoryItem(activeMemoryPath) || firstMemoryItem();
  }

  /**
   * @param {Record<string, any> | null} memoryItem
   * @param {string} status
   */
  async function updateMemoryStatus(memoryItem, status) {
    if (!route.scenarioId || !currentSessionId || !memoryItem || memoryStatusSaving) return;
    const parts = String(memoryItem.path || "").split("/");
    const kind = parts[1] || "";
    const filename = parts[2] || "";
    const memoryId = filename.replace(/\.md$/, "");
    if (!kind || !memoryId) return;
    memoryStatusSaving = true;
    memoryError = "";
    memoryStatusMessage = "";
    try {
      await updateMemoryMetadata(route.scenarioId, kind, memoryId, { status });
      memoryStatusMessage = translateNow("settings.memoryStatusSaved");
      await loadMemoryList(route.scenarioId, currentSessionId, memoryItem.path);
      await loadRagStatus(route.scenarioId);
    } catch (caught) {
      memoryError = caught instanceof Error ? caught.message : translateNow("settings.memoryStatusError");
    } finally {
      memoryStatusSaving = false;
    }
  }

  /** @param {string | undefined} sourcePath */
  function openRagSource(sourcePath) {
    if (!route.scenarioId || !sourcePath || !onNavigate.openScenarioEdit) {
      return;
    }
    onNavigate.openScenarioEdit(route.scenarioId, sourcePath);
  }

  function stateTopLevelKeys() {
    return Object.keys(state || {}).slice(0, 10);
  }

  /** @param {string} sessionId */
  async function copyBranchSessionId(sessionId) {
    try {
      await navigator.clipboard?.writeText(sessionId);
      turnNotice = translateNow("session.sessionIdCopied", { sessionId });
    } catch {
      turnNotice = `Session ID: ${sessionId}`;
    }
  }

  /** @param {Record<string, any>} branch */
  async function renameBranchSession(branch) {
    if (!route.scenarioId || !branch?.session_id || sending) return;
    const currentName = branch.display_name || branch.session_id;
    const nextName = window.prompt("Branch name", currentName);
    if (nextName === null) return;
    const trimmed = nextName.trim();
    if (!trimmed || trimmed === currentName) return;
    try {
      await updateSessionSettings(route.scenarioId, branch.session_id, { display_name: trimmed });
      await loadTimeline(route.scenarioId, currentSessionId);
      turnNotice = translateNow("session.branchNameUpdated", { name: trimmed });
    } catch (caught) {
      error = caught instanceof Error ? caught.message : translateNow("session.branchNameUpdateError");
    }
  }

  function lastUpdatedAt() {
    return sessionMetadata.updated_at || sessionMetadata.created_at || translateNow("common.unrecorded");
  }

  /** @param {"prev" | "next"} direction */
  async function switchStarting(direction) {
    if (!route.scenarioId || !currentSessionId || switchingStarting || startings.length <= 1) return;
    const currentStarting = messages.find((/** @type {any} */ m) => m.is_starting);
    const currentId = currentStarting?.starting_id || startings[0]?.id;
    const currentIndex = startings.findIndex((/** @type {any} */ s) => s.id === currentId);
    const next = (currentIndex + (direction === "next" ? 1 : -1) + startings.length) % startings.length;
    switchingStarting = true;
    try {
      await updateSessionStarting(route.scenarioId, currentSessionId, startings[next].id);
      await reloadSession(route.scenarioId, currentSessionId);
    } catch (caught) {
      error = caught instanceof Error ? caught.message : translateNow("session.switchStartingError");
    } finally {
      switchingStarting = false;
    }
  }

  /** @param {"persona" | "roleplay" | "state"} kind */
  function openPicker(kind) {
    pickerState.open(kind);
    if (isMobile && currentSessionId) layout.setSideOpen(false);
  }

  /** @param {"state" | "timeline"} panel */
  function openRightPanel(panel) {
    layout.openRightPanel(panel);
  }

</script>

<main class:mobile-right-open={$layout.rightOpen} class:without-side={!$layout.sideOpen} class="session-shell">
  {#if showSessionSide && isMobile && $layout.sideOpen}
    <button class="mobile-overlay-scrim" type="button" aria-label={$t("session.closeSideCol")} onclick={() => layout.setSideOpen(false)}></button>
  {/if}
  {#if showSessionSide && $layout.sideOpen}
    <aside class="session-side" aria-labelledby="session-side-heading">
      <div class="brand-block">
        <div>
          <p class="eyebrow">Obsidian-first RP</p>
          <h1 id="session-side-heading">Locus RP</h1>
        </div>
        <button class="icon-button" type="button" title={$t("session.closeSideCol")} onclick={() => layout.setSideOpen(false)}>
          <PanelLeftClose size={18} aria-hidden="true" />
        </button>
      </div>

      <section class="control-group" aria-labelledby="profile-heading">
        <h2 id="profile-heading">Profiles</h2>
        <div class="setting-stack">
          <button class="setting-card setting-card-button" type="button" onclick={() => openPicker("persona")}>
            <div class="setting-card-head">
              <span>Persona</span>
              <span class="card-action-label">{$t("session.change")}</span>
            </div>
            <strong>{personaName($selection, $selection.selectedPersona)}</strong>
            <small>{route.scenarioId || $t("session.noScenarioId")}</small>
          </button>
          <button class="setting-card setting-card-button" type="button" onclick={() => openPicker("roleplay")}>
            <div class="setting-card-head">
              <span>GM profile</span>
              <span class="card-action-label">{$t("session.change")}</span>
            </div>
            <strong>{$selection.selectedRpProfile}</strong>
            <small>{profileModel($selection, $selection.selectedRpProfile)}</small>
          </button>
          <button class="setting-card setting-card-button" type="button" onclick={() => openPicker("state")}>
            <div class="setting-card-head">
              <span>State profile</span>
              <span class="card-action-label">{$t("session.change")}</span>
            </div>
            <strong>{$selection.selectedStateProfile}</strong>
            <small>{profileModel($selection, $selection.selectedStateProfile)}</small>
          </button>
        </div>
      </section>

      {#if !currentSessionId}
        <section class="control-group" aria-labelledby="starting-heading">
          <h2 id="starting-heading">Starting</h2>
          {#if startings.length}
            <label class="setting-card">
              <span>{$t("session.startSituation")}</span>
              <select class="compact-input" bind:value={selectedStartingId}>
                {#each startings as starting}
                  <option value={starting.id}>{starting.name || starting.id}</option>
                {/each}
              </select>
              <small>{startings.find((/** @type {any} */ s) => s.id === selectedStartingId)?.name || selectedStartingId}</small>
            </label>
          {:else}
            <p class="notice">{$t("session.noStarting")}</p>
          {/if}
        </section>
      {/if}

      {#if !currentSessionId}
        <button class="primary-action" type="button" disabled={loading} onclick={() => void createSelectedSession()}>
          {$t("session.selectAndStart")}
        </button>
      {/if}

    </aside>
  {/if}

  <section class="session-view">
    <header class="session-header">
      <div class="session-title-group">
        {#if showSessionSide && !$layout.sideOpen}
          <button class="icon-button" type="button" title={$t("session.openSideCol")} onclick={() => layout.setSideOpen(true)}>
            <PanelLeftOpen size={18} aria-hidden="true" />
          </button>
        {/if}
        <div>
          <p class="eyebrow">Session</p>
          <h2 id="workspace-heading">{currentSessionId || "New Session"}</h2>
        </div>
      </div>
      <button class="icon-button" type="button" title="Front Page" onclick={onNavigate.openHome}>
        <ArrowLeft size={18} aria-hidden="true" />
      </button>
    </header>

    {#if error}
      <p class="notice error-notice">{error}</p>
    {/if}
    {#if turnNotice}
      <p class="notice">{turnNotice}</p>
    {/if}

    {#if loading}
      <p class="notice">{$t("session.loadingSession")}</p>
    {:else if !currentSessionId}
      {#if isMobile}
        <section class="panel mobile-session-start-panel" aria-labelledby="new-session-heading">
          <div class="panel-header compact">
            <div>
              <p class="eyebrow">New Session</p>
              <h3 id="new-session-heading">{$t("session.startSetup")}</h3>
            </div>
          </div>

          <div class="mobile-start-body">
            <label class="setting-card">
              <span>Starting</span>
              {#if startings.length}
                <select class="compact-input" bind:value={selectedStartingId}>
                  {#each startings as starting}
                    <option value={starting.id}>{starting.name || starting.id}</option>
                  {/each}
                </select>
                <small>{startings.find((/** @type {any} */ s) => s.id === selectedStartingId)?.name || selectedStartingId}</small>
              {:else}
                <small>{$t("session.noStarting")}</small>
              {/if}
            </label>
          </div>

          <div class="mobile-start-footer">
            <div class="setting-stack">
              <button class="setting-card setting-card-button" type="button" onclick={() => openPicker("persona")}>
                <div class="setting-card-head">
                  <span>Persona</span>
                  <span class="card-action-label">{$t("session.change")}</span>
                </div>
                <strong>{personaName($selection, $selection.selectedPersona)}</strong>
                <small>{route.scenarioId || $t("session.noScenarioId")}</small>
              </button>
              <button class="setting-card setting-card-button" type="button" onclick={() => openPicker("roleplay")}>
                <div class="setting-card-head">
                  <span>GM profile</span>
                  <span class="card-action-label">{$t("session.change")}</span>
                </div>
                <strong>{$selection.selectedRpProfile}</strong>
                <small>{profileModel($selection, $selection.selectedRpProfile)}</small>
              </button>
              <button class="setting-card setting-card-button" type="button" onclick={() => openPicker("state")}>
                <div class="setting-card-head">
                  <span>State profile</span>
                  <span class="card-action-label">{$t("session.change")}</span>
                </div>
                <strong>{$selection.selectedStateProfile}</strong>
                <small>{profileModel($selection, $selection.selectedStateProfile)}</small>
              </button>
            </div>
            <button class="primary-action" type="button" disabled={loading} onclick={() => void createSelectedSession()}>
              {$t("session.selectAndStart")}
            </button>
          </div>
        </section>
      {:else}
        <section class="panel route-panel" aria-labelledby="new-session-heading">
          <h3 id="new-session-heading">New Session</h3>
          <p>{$t("session.selectToStart")}</p>
        </section>
      {/if}
    {:else}
      <div class="session-workspace" class:desktop-right-closed={!isMobile && !$layout.rightOpen}>
        <div class="mobile-right-tabs" aria-label={$t("session.stateAndTimeline")}>
          <button
            class:active={$layout.rightOpen && $layout.rightPanel === "state"}
            type="button"
            aria-label={$t("session.openState")}
            onclick={() => openRightPanel("state")}
          >
            State
          </button>
          <button
            class:active={$layout.rightOpen && $layout.rightPanel === "timeline"}
            type="button"
            aria-label={$t("session.openTimeline")}
            onclick={() => openRightPanel("timeline")}
          >
            Timeline
          </button>
        </div>
        {#if isMobile && $layout.rightOpen}
          <button class="mobile-overlay-scrim right" type="button" aria-label={$t("session.closeRightPanel")} onclick={() => layout.setRightOpen(false)}></button>
        {/if}
        <section class="panel chat-panel" aria-labelledby="chat-heading">
          <div class="panel-header compact">
            <h3 id="chat-heading">Chat</h3>
            <div class="chat-top-tools" aria-label={$t("session.sessionOps")}>
              <span>{route.scenarioId || $t("session.noScenarioId")}</span>
              {#if !isMobile && !$layout.rightOpen}
                <button class="icon-button" type="button" title={$t("session.openRightPanel")} aria-label={$t("session.openRightPanel")} onclick={() => layout.setRightOpen(true)}>
                  <PanelRightOpen size={17} aria-hidden="true" />
                </button>
              {/if}
              <button class="icon-button" type="button" title={$t("session.sessionInfo")} aria-label={$t("session.sessionInfo")} onclick={openSessionInfo}>
                <Info size={17} aria-hidden="true" />
              </button>
              <button class="icon-button" type="button" title={$t("session.sessionSettings")} aria-label={$t("session.sessionSettings")} onclick={openSessionSettings}>
                <Settings size={17} aria-hidden="true" />
              </button>
            </div>
          </div>

          <div class="chat-log" aria-live="polite" bind:this={chatLogElement} onscroll={handleChatLogScroll}>
            {#if messages.length}
              {#if logPagination.has_more_before}
                <div class="log-page-controls">
                  <button class="tool-button" type="button" disabled={loadingOlderLog || sending} onclick={() => void loadOlderLog()}>
                    {loadingOlderLog ? $t("session.loadingMore") : $t("session.loadOlderTurns", { count: LOG_TURN_PAGE_SIZE })}
                  </button>
                  <span>
                    Turn {logPagination.min_turn ?? "-"}-{logPagination.max_turn ?? "-"} / {logPagination.total_turns ?? "-"} turns
                  </span>
                </div>
              {/if}
              {#each messages as message}
                <article id="message-turn-{message.turn}-{message.role}" class:assistant-message={message.role === "assistant"} class="chat-message">
                  <div class="message-bubble">
                    <header>
                      <span>{message.role === "assistant" ? "GM" : userLabel}</span>
                      <span class="message-meta-line">
                        {#if message.turn}
                          <span>Turn {message.turn}</span>
                        {/if}
                        {#if message.role === "assistant" && formatResponseDuration(message)}
                          <span title="LLM response time">{formatResponseDuration(message)}</span>
                        {/if}
                      </span>
                    </header>
                    {#if editMessageTurn === message.turn && editMessageRole === message.role}
                      <div class="message-editor" style="margin-top: 8px;">
                        <textarea class="settings-textarea" bind:value={editDraft} rows={Math.max(3, (editDraft || "").split("\n").length)}></textarea>
                        <div class="editor-actions memory-actions" style="margin-top: 8px; justify-content: flex-end;">
                          <button class="tool-button" type="button" disabled={editSaving} onclick={cancelEditing}>{$t("common.cancel")}</button>
                          <button class="primary-button" type="button" disabled={editSaving} onclick={() => saveEdit(message)}>
                            {shouldBranchFromEditedUserMessage(message) ? $t("session.branchAndLoad") : $t("common.saveChanges")}
                          </button>
                        </div>
                      </div>
                    {:else if displaySegments(message).length}
                      <div class="message-segments">
                        {#each displaySegments(message) as segment, segmentIndex}
                          {#if segment.type === "image"}
                            {#if segment.url && segment.exists !== false}
                              <img src={segment.url} alt={segment.path || "scenario image"} loading="lazy" />
                            {:else}
                              <span class="missing-image">
                                <ImageOff size={16} aria-hidden="true" />
                                {segment.path || "missing image"}
                              </span>
                          {/if}
                        {:else if segment.type === "character_dialogue"}
                          <div class="bustup-dialogue">
                            <img src={segment.character.bustup_url} alt={segment.speaker} loading="lazy" />
                            <div class="dialogue-bubble">
                              <strong>{segment.speaker}</strong>
                              <div class="markdown-body">{@html renderMarkdown(resolveUser(segment.dialogue))}</div>
                            </div>
                          </div>
                        {:else if segment.type === "meta"}
                          <div class="meta-segment">
                            {#if segment.live}
                              <div class="meta-live-label">{$t("session.reasoning")}<span class="loading-dots" aria-hidden="true"></span></div>
                              <div class="meta-content meta-content--live markdown-body">
                                {@html renderMarkdown(resolveUser(segment.content))}
                              </div>
                            {:else}
                              <button
                                class="meta-toggle"
                                type="button"
                                aria-expanded={expandedMetaSegments[metaSegmentKey(message, segmentIndex)] === true ? "true" : "false"}
                                onclick={() => toggleMetaSegment(metaSegmentKey(message, segmentIndex))}
                              >
                                {expandedMetaSegments[metaSegmentKey(message, segmentIndex)] === true ? $t("session.hideReasoning") : $t("session.showReasoning")}
                              </button>
                              {#if expandedMetaSegments[metaSegmentKey(message, segmentIndex)] === true}
                                <div class="meta-content markdown-body">
                                  {@html renderMarkdown(resolveUser(segment.content))}
                                </div>
                              {/if}
                            {/if}
                          </div>
                        {:else}
                            <div class="markdown-body">{@html renderMarkdown(resolveUser(segment.content))}</div>
                        {/if}
                      {/each}
                      {#if message.streaming}
                        <div class="stream-loading-indicator" aria-label={$t("session.waitingGM")}>
                          <Wand2 size={15} aria-hidden="true" />
                          <span>{message.content ? $t("session.generating") : $t("session.waitingStream")}</span>
                          <span class="loading-dots" aria-hidden="true"></span>
                        </div>
                      {/if}
                    </div>
                  {/if}
                </div>
                  <div class="message-actions" aria-label={message.role === "assistant" ? $t("session.gmActions") : $t("session.userActions")}>
                    {#if message.role === "assistant"}
                      {#if message.is_starting}
                        {#if startings.length > 1 && (sessionMetadata?.turn_count ?? 1) === 0}
                          <div class="candidate-switcher" aria-label={$t("session.switchStartingLabel")}>
                            <button class="icon-button message-action-button" type="button" title={$t("session.prevStarting")} aria-label={$t("session.prevStarting")} disabled={switchingStarting} onclick={() => void switchStarting("prev")}>
                              <ChevronLeft size={15} aria-hidden="true" />
                            </button>
                            <span>{startings.findIndex((/** @type {any} */ s) => s.id === message.starting_id) + 1}/{startings.length}</span>
                            <button class="icon-button message-action-button" type="button" title={$t("session.nextStarting")} aria-label={$t("session.nextStarting")} disabled={switchingStarting} onclick={() => void switchStarting("next")}>
                              <ChevronRight size={15} aria-hidden="true" />
                            </button>
                          </div>
                        {/if}
                      {:else}
                        {#if message.turn === latestTurn}
                          <button class="icon-button message-action-button" type="button" title={$t("session.continueGen")} aria-label={$t("session.continueGen")} disabled={sending} onclick={() => handleContinue(message)}>
                            <ChevronDown size={15} aria-hidden="true" />
                          </button>
                          <button class="icon-button message-action-button" type="button" title={$t("session.regenerate")} aria-label={$t("session.regenerate")} disabled={sending} onclick={() => handleRegenerate(message)}>
                            <RefreshCcw size={15} aria-hidden="true" />
                          </button>
                          <button class="icon-button message-action-button" type="button" title={$t("session.delete")} aria-label={$t("session.delete")} disabled={deletingTurn === message.turn} onclick={() => handleDeleteMessage(message)}>
                            <Trash2 size={15} aria-hidden="true" />
                          </button>
                        {/if}
                        <button class="icon-button message-action-button" type="button" title={$t("session.edit")} aria-label={$t("session.edit")} onclick={() => startEditing(message)}>
                          <Pencil size={15} aria-hidden="true" />
                        </button>
                        <button
                          class="icon-button message-action-button"
                          type="button"
                          title={$t("session.branchFromHere")}
                          aria-label={$t("session.branchFromHere")}
                          disabled={sending || message.turn == null}
                          onclick={() => message.turn != null && openBranchDialog(message.turn)}
                        >
                          <FileStack size={15} aria-hidden="true" />
                        </button>
                        {#if message.candidates && message.candidates.length > 1}
                          <div class="candidate-switcher" aria-label={$t("session.switchCandidate")}>
                            <button class="icon-button message-action-button" type="button" title={$t("session.prevCandidate")} aria-label={$t("session.prevCandidate")} onclick={() => handleSwitchCandidate(message, "prev")}>
                              <ChevronLeft size={15} aria-hidden="true" />
                            </button>
                            <span>{(message.active_candidate_index || 0) + 1}/{message.candidates.length}</span>
                            <button class="icon-button message-action-button" type="button" title={$t("session.nextCandidate")} aria-label={$t("session.nextCandidate")} onclick={() => handleSwitchCandidate(message, "next")}>
                              <ChevronRight size={15} aria-hidden="true" />
                            </button>
                          </div>
                        {/if}
                      {/if}
                    {:else}
                      {#if message.turn === latestTurn}
                        <button class="icon-button message-action-button" type="button" title={$t("session.delete")} aria-label={$t("session.delete")} disabled={deletingTurn === message.turn} onclick={() => handleDeleteMessage(message)}>
                          <Trash2 size={15} aria-hidden="true" />
                        </button>
                      {/if}
                      <button class="icon-button message-action-button" type="button" title={$t("session.edit")} aria-label={$t("session.edit")} onclick={() => startEditing(message)}>
                        <Pencil size={15} aria-hidden="true" />
                      </button>
                    {/if}
                  </div>
                </article>
              {/each}
              {#if logPagination.has_more_after}
                <div class="log-page-controls">
                  <button class="tool-button" type="button" disabled={loadingOlderLog || sending} onclick={() => void loadLatestLog()}>
                    {$t("session.latestTurn")}
                  </button>
                  <span>
                    Turn {logPagination.min_turn ?? "-"}-{logPagination.max_turn ?? "-"} / {logPagination.total_turns ?? "-"} turns
                  </span>
                </div>
              {/if}
            {:else}
              <p class="notice">{$t("session.noLog")}</p>
            {/if}
            {#if sending && (!$preferences.streamEnabled || turnJobPolling)}
              <div class="inline-loading-indicator" aria-label={$t("session.generatingResponse")}>
                <Wand2 size={16} aria-hidden="true" />
                <span>{$t("session.generatingResponse")}</span>
                <span class="loading-dots" aria-hidden="true"></span>
              </div>
            {/if}
            {#if stateUpdating}
              <div class="inline-loading-indicator" aria-label={$t("session.updatingState")}>
                <Wand2 size={16} aria-hidden="true" />
                <span>{$t("session.updatingState")}</span>
                <span class="loading-dots" aria-hidden="true"></span>
              </div>
            {/if}
          </div>

          {#if newMessageBadge}
            <div class="new-message-badge-bar">
              <button class="new-message-badge" type="button" onclick={() => void dismissNewMessageBadge()}>
                <ChevronDown size={14} aria-hidden="true" /> {$t("session.newMessages")}
              </button>
            </div>
          {/if}

          <form class="composer" onsubmit={(event) => { event.preventDefault(); void submitTurn(); }}>
            <div class="textarea-wrapper">
              <textarea
                bind:this={composer}
                bind:value={input}
                disabled={!currentSessionId || sending || stateUpdating}
                placeholder={currentSessionId ? $t("session.inputPlaceholder") : $t("session.creatingSessionPlaceholder")}
                rows="1"
                onkeydown={handleKeydown}
              ></textarea>
              <div class="composer-tools-inline">
                <button type="button" title="「」" onclick={() => wrapSelection("quote")}>
                  <Braces size={16} aria-hidden="true" />
                </button>
                <button type="button" title="*" onclick={() => wrapSelection("asterisk")}>
                  <Asterisk size={16} aria-hidden="true" />
                </button>
              </div>
            </div>
            <div class="composer-footer-actions">
              <label class="send-mode-toggle" title={sending ? $t("session.streamToggleSending") : $t("session.streamToggleTitle")}>
                <input type="checkbox" checked={$preferences.streamEnabled} disabled={sending || stateUpdating} onchange={(event) => preferences.setStreamEnabled(event.currentTarget.checked)} />
                <span>Stream</span>
              </label>
              <label class="send-mode-toggle" title={$t("session.enterToggleTitle")}>
                <input type="checkbox" checked={$preferences.sendOnEnter} onchange={(event) => preferences.setSendOnEnter(event.currentTarget.checked)} />
                <span>{$t("session.sendOnEnter")}</span>
              </label>
              <button
                class="send-button"
                type={sending ? "button" : "submit"}
                disabled={!currentSessionId || stateUpdating || (!sending && !input.trim())}
                onclick={() => sending && stopGeneration()}
              >
                {#if sending}
                  <Square size={16} aria-hidden="true" />
                  {$t("session.stop")}
                {:else}
                  <Send size={16} aria-hidden="true" />
                  {$t("session.send")}
                {/if}
              </button>
            </div>
          </form>
        </section>

        <aside class="panel state-panel" aria-labelledby="state-heading">
          <div class="panel-header compact">
            <h3 id="state-heading">{$layout.rightPanel === "state" ? "State" : "Timeline"}</h3>
            <div class="segmented-control">
              <button class:selected={$layout.rightPanel === "state"} type="button" onclick={() => layout.setRightPanel("state")}>
                State
              </button>
              <button
                class:selected={$layout.rightPanel === "timeline"}
                type="button"
                onclick={() => layout.setRightPanel("timeline")}
              >
                Timeline
              </button>
            </div>
            <button class="icon-button mobile-overlay-close" type="button" title={$t("session.closeRightPanel")} onclick={() => layout.setRightOpen(false)}>
              <ChevronRight size={17} aria-hidden="true" />
            </button>
          </div>
          {#if $layout.rightPanel === "state"}
            <div class="state-panel-toolbar">
              <span class="state-scope-label">{currentSessionId ? $t("session.sessionState") : $t("session.scenarioState")}</span>
              <button type="button" onclick={() => route.scenarioId && loadState(route.scenarioId, currentSessionId)}>{$t("common.reload")}</button>
            </div>
            <StatePanel {state} scenarioId={route.scenarioId || ""} stateJsonStr={stateJson()} />
          {:else}
            <div class="timeline-column">
              <TimelinePanel
                items={timeline}
                {currentSessionId}
                metadata={timelineMetadata}
                onJump={handleJumpToTurn}
                onBranch={openBranchDialog}
                onToggleBookmark={handleToggleBookmark}
                onOpenSession={(sessionId) => route.scenarioId && onNavigate.openSession(route.scenarioId, sessionId)}
                onCopySessionId={copyBranchSessionId}
                onRenameBranch={renameBranchSession}
              />
            </div>
          {/if}
        </aside>
      </div>
    {/if}
  </section>

  {#if $pickerState.kind}
    <PersonaProfilePickerModal
      {pickerState}
      {selection}
      onChooseRpProfile={handleSessionRpProfileChange}
      onChooseStateProfile={handleSessionStateProfileChange}
    />
  {/if}

  {#if sessionModal}
    <div class="modal-backdrop">
      <button class="modal-scrim" type="button" aria-label={$t("common.close")} onclick={closeSessionModal}></button>
      <div
        class="session-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="session-modal-heading"
        tabindex="-1"
      >
        <div class="panel-header compact">
          <h3 id="session-modal-heading">{sessionModal === "info" ? "Session Info" : "Session Settings"}</h3>
          <button class="icon-button" type="button" title={$t("common.close")} onclick={closeSessionModal}>×</button>
        </div>

        {#if sessionModal === "info"}
          <div class="modal-grid two-column">
            <section class="modal-section">
              <h4>Identity</h4>
              <dl class="info-list">
                <div><dt>Session</dt><dd>{currentSessionId}</dd></div>
                <div><dt>Scenario</dt><dd>{route.scenarioId || $t("session.unspecified")}</dd></div>
                <div><dt>Display name</dt><dd>{sessionMetadata.display_name || currentSessionId}</dd></div>
                <div><dt>Updated</dt><dd>{lastUpdatedAt()}</dd></div>
              </dl>
            </section>

            <section class="modal-section">
              <h4>Profiles</h4>
              <dl class="info-list">
                <div><dt>Persona</dt><dd>{sessionMetadata.persona_id || $selection.selectedPersona}</dd></div>
                <div><dt>GM profile</dt><dd>{sessionMetadata.rp_profile_id || $selection.selectedRpProfile}</dd></div>
                <div><dt>State profile</dt><dd>{sessionMetadata.summary_profile_id || $t("session.unset")}</dd></div>
                <div><dt>Turns</dt><dd>{sessionMetadata.turn_count ?? messages.length}</dd></div>
              </dl>
            </section>

            <section class="modal-section">
              <h4>Branch</h4>
              <dl class="info-list">
                <div><dt>Parent</dt><dd>{sessionMetadata.parent_session_id || $t("session.none")}</dd></div>
                <div><dt>Branched turn</dt><dd>{sessionMetadata.branched_from_turn ?? $t("session.none")}</dd></div>
                <div><dt>State snapshot</dt><dd>{sessionMetadata.state_snapshot_available === false ? "fallback" : "available"}</dd></div>
              </dl>
            </section>

            <section class="modal-section">
              <h4>State</h4>
              <dl class="info-list">
                <div><dt>Scope</dt><dd>session</dd></div>
                <div><dt>Top keys</dt><dd>{stateTopLevelKeys().join(", ") || $t("session.none")}</dd></div>
                <div><dt>Timeline items</dt><dd>{timeline.length}</dd></div>
                <div><dt>Log entries</dt><dd>{messages.length}</dd></div>
              </dl>
            </section>
          </div>
        {:else}
          <SessionSettingsModal
            scenarioId={route.scenarioId || ""}
            sessionId={currentSessionId || ""}
            bind:sessionNoteDraft
            bind:sceneNoteDraft
            bind:activeMemoryPath
            {settingsSaving}
            {settingsMessage}
            {saveSessionSettings}
            {pinsLoading}
            {pinsSaving}
            {pinsMessage}
            {pinsData}
            {toggleMod}
            {togglePinnedCharacter}
            {promptPreviewLoading}
            {promptPreviewError}
            {promptPreview}
            {openRagSource}
            {ragStatusLoading}
            {ragStatusError}
            {ragStatus}
            {ragRebuildRunning}
            {ragRebuildMessage}
            {rebuildRagIndex}
            {memoryLoading}
            {memoryError}
            {memoryList}
            {memoryStatusSaving}
            {memoryStatusMessage}
            {selectedMemoryItem}
            {loadMemoryList}
            {updateMemoryStatus}
          />
        {/if}
      </div>
    </div>
  {/if}

  {#if branchTurnDraft !== null}
    <div class="modal-backdrop">
      <button class="modal-scrim" type="button" aria-label={$t("common.close")} onclick={closeBranchDialog}></button>
      <div class="session-modal" role="dialog" aria-modal="true" aria-labelledby="branch-modal-heading" tabindex="-1">
        <div class="panel-header compact">
          <h3 id="branch-modal-heading">{$t("session.branchCreate")}</h3>
          <button class="icon-button" type="button" title={$t("common.close")} disabled={branchSaving} onclick={closeBranchDialog}>×</button>
        </div>
        <div class="modal-grid">
          <section class="modal-section">
            <h4>Checkpoint</h4>
            <dl class="info-list compact-list">
              <div><dt>Turn</dt><dd>{branchTurnDraft}</dd></div>
              <div><dt>State snapshot</dt><dd>{branchSnapshotAvailable(branchTurnDraft) ? "available" : "fallback"}</dd></div>
            </dl>
            {#if branchError}
              <p class="placeholder-copy error-copy">{branchError}</p>
            {/if}
            <label class="setting-card">
              <span>Branch name</span>
              <input class="compact-input" bind:value={branchNameDraft} placeholder={defaultBranchName(branchTurnDraft)} />
            </label>
            <div class="modal-actions">
              <button type="button" disabled={branchSaving} onclick={closeBranchDialog}>{$t("common.cancel")}</button>
              <button type="button" disabled={branchSaving} onclick={() => branchTurnDraft !== null && handleBranchFromTurn(branchTurnDraft)}>
                {branchSaving ? $t("common.creating") : $t("session.createBranch")}
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>
  {/if}
</main>

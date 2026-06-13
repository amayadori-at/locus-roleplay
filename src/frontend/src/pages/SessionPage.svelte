<script>
  import { ArrowLeft, ChevronRight, PanelLeftOpen } from "lucide-svelte";
  import { onDestroy, onMount, tick } from "svelte";
  import {
    createBranchSession,
    createSession,
    getScenarioRagStatus,
    getScenarioState,
    getSessionLog,
    getSessionPromptPreview,
    getSessionTimeline,
    listPersonas,
    listProfiles,
    listScenarioMemory,
    listScenarioCharacterBustups,
    listScenarioStartings,
    rebuildScenarioRagIndex,
    updateSessionSettings,
    updateSessionMessage,
    deleteSessionMessage,
    switchAssistantCandidate,
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
  import { createTurnEngine } from "../lib/session/turnEngine.svelte.js";
  import { shouldSubmitComposer, wrapComposerSelection } from "../lib/sessionComposer.js";
  import {
    mergeLogPagination,
    mergeOlderLogMessages,
    nextAssistantCandidateIndex
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
  import ChatPanel from "../lib/session/ChatPanel.svelte";
  import SessionSidebar from "../lib/session/SessionSidebar.svelte";

  /**
   * @typedef {{
   *   scenarioId?: string,
   *   sessionId?: string
   * }} SessionRoute
   *
   */

  /**
   * @type {{
   *   route: SessionRoute,
   *   onNavigate?: {
   *     openHome: () => void,
   *     openSession: (scenarioId: string, sessionId?: string) => void,
   *     openScenarioEdit?: (scenarioId: string, sourcePath?: string) => void,
   *   },
   * }}
   */
  let { route, onNavigate = {
    openHome: () => {},
    openSession: () => {},
    openScenarioEdit: () => {}
  } } = $props();

  const LOG_TURN_PAGE_SIZE = 10;

  /** @param {string} content */
  function resolveUser(content) {
    if (!content.includes("{{user}}")) return content;
    return content.replaceAll("{{user}}", userLabel);
  }

  /** @type {Array<Record<string, any>>} */
  let timeline = $state([]);
  /** @type {Record<string, any>} */
  let timelineMetadata = $state({});
  // Named sessionState (not `state`): a binding called state would shadow the $state rune.
  let sessionState = $state(/** @type {Record<string, any> | null} */ (null));
  let currentSessionId = $state("");
  let loading = $state(false);
  let loadingOlderLog = $state(false);
  let isMobile = $state(false);
  let activeAssistantCandidate = $state(1);
  let assistantCandidateCount = $state(1);
  /** @type {Record<string, boolean>} */
  let expandedMetaSegments = $state({});
  /** @type {Record<string, any>} */
  let sessionMetadata = $state({});
  /** @type {Record<string, any>} */
  let logPagination = $state({});
  /** @type {"info" | "settings" | ""} */
  let sessionModal = $state("");
  let sessionNoteDraft = $state("");
  let sceneNoteDraft = $state("");
  let settingsSaving = $state(false);
  let settingsMessage = $state("");
  let pinsData = $state(/** @type {Record<string, any> | null} */ (null));
  let pinsLoading = $state(false);
  let pinsSaving = $state(false);
  let pinsMessage = $state("");
  let editMessageTurn = $state(/** @type {number | null} */ (null));
  let editMessageRole = $state("");
  let editDraft = $state("");
  let editSaving = $state(false);
  let branchTurnDraft = $state(/** @type {number | null} */ (null));
  let branchNameDraft = $state("");
  let branchSaving = $state(false);
  let branchError = $state("");
  let deletingTurn = $state(/** @type {number | null} */ (null));
  let deletingRole = $state("");
  let promptPreviewLoading = $state(false);
  let promptPreviewError = $state("");
  let promptPreview = $state(/** @type {Record<string, any> | null} */ (null));
  let ragStatusLoading = $state(false);
  let ragStatusError = $state("");
  let ragStatus = $state(/** @type {Record<string, any> | null} */ (null));
  let memoryLoading = $state(false);
  let memoryError = $state("");
  let memoryList = $state(/** @type {Record<string, any> | null} */ (null));
  let memoryStatusSaving = $state(false);
  let memoryStatusMessage = $state("");
  let activeMemoryPath = $state("");
  let ragRebuildRunning = $state(false);
  let ragRebuildMessage = $state("");
  /** @type {Array<Record<string, any>>} */
  let startings = $state([]);
  /** @type {Array<Record<string, any>>} */
  let characterBustups = $state([]);
  let selectedStartingId = $state("");
  let switchingStarting = $state(false);
  let loadedKey = $state("");
  const selection = createSessionSelectionStore();
  const layout = createSessionLayoutStore();
  const pickerState = createSessionPickerStore();
  const preferences = createSessionPreferencesStore();
  const userLabel = $derived(($selection.selectedPersona && $selection.selectedPersona !== EMPTY_SELECTION)
    ? personaName($selection, $selection.selectedPersona)
    : "User");

  const engine = createTurnEngine({
    preferences,
    loadLog,
    loadTimeline,
    loadState,
    reloadSession,
    scrollToBottom,
    refreshSettingsPanes: () => {
      if (sessionModal === "settings" && route.scenarioId && currentSessionId) {
        return Promise.all([loadPromptPreview(route.scenarioId, currentSessionId), loadRagStatus(route.scenarioId)]);
      }
    }
  });

  function submitTurn() {
    return engine.submitTurn(route.scenarioId || "", currentSessionId);
  }

  /** @param {Record<string, any>} message */
  function handleRegenerate(message) {
    return engine.handleRegenerate(route.scenarioId || "", currentSessionId, message);
  }

  /** @param {Record<string, any>} message */
  function handleContinue(message) {
    return engine.handleContinue(route.scenarioId || "", currentSessionId, message);
  }
  const BRANCH_EDIT_PRESET_PREFIX = "locus-rp:branch-edit-preset:";
  let composer = $state(/** @type {HTMLTextAreaElement | null} */ (null));
  let chatLogElement = $state(/** @type {HTMLElement | null} */ (null));

  const selectedMemoryItem = $derived(activeMemoryItem());
  const showSessionSide = $derived(!isMobile || Boolean(currentSessionId));
  $effect(() => {
    if (!showSessionSide && $layout.sideOpen) layout.setSideOpen(false);
  });

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
    engine.newMessageBadge = false;
    await scrollToBottom();
  }

  function handleChatLogScroll() {
    if (!chatLogElement) return;
    const { scrollTop, scrollHeight, clientHeight } = chatLogElement;
    if (scrollHeight - scrollTop - clientHeight < 40) {
      engine.newMessageBadge = false;
    }
    if (scrollTop < 120 && logPagination.has_more_before && !loadingOlderLog && !engine.sending) {
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
      engine.messages = payload.log || [];
      logPagination = payload.pagination || {};
    } catch (caught) {
      engine.error = caught instanceof Error ? caught.message : translateNow("session.loadLogError");
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
    if (!route.scenarioId || !currentSessionId || engine.sending) {
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
    if (!route.scenarioId || !currentSessionId || engine.sending) {
      return;
    }
    const displayName = branchNameDraft.trim() || defaultBranchName(turn);
    branchSaving = true;
    branchError = "";
    engine.error = "";
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
        engine.turnNotice = translateNow("session.branchStateFallback");
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
    if (!route.scenarioId || !currentSessionId || engine.sending) {
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
      engine.error = caught instanceof Error ? caught.message : translateNow("session.bookmarkSaveError");
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
      engine.error = caught instanceof Error ? caught.message : translateNow("session.profileUpdateError");
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
      engine.error = caught instanceof Error ? caught.message : translateNow("session.profileUpdateError");
    }
  }

  const currentRouteKey = $derived(`${route.scenarioId || ""}:${route.sessionId || ""}`);
  $effect(() => {
    if (currentRouteKey && currentRouteKey !== loadedKey) {
      void initialize(currentRouteKey);
    }
  });

  /** @param {string} routeKey */
  async function initialize(routeKey) {
    engine.abortPendingTurn("route_change");
    loadedKey = routeKey;
    engine.error = "";
    engine.turnNotice = "";
    engine.messages = [];
    logPagination = {};
    timeline = [];
    timelineMetadata = {};
    sessionState = null;
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
      engine.error = translateNow("session.noScenario");
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
      await engine.resumePendingJobs(route.scenarioId, currentSessionId);
      applyBranchEditPreset(route.scenarioId, currentSessionId);
    } catch (caught) {
      engine.error = caught instanceof Error ? caught.message : translateNow("session.loadSessionError");
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
      engine.error = translateNow("session.noScenario");
      return;
    }
    if (!$selection.selectedPersona || $selection.selectedPersona === EMPTY_SELECTION) {
      engine.error = translateNow("session.noPersona");
      return;
    }
    if (!$selection.selectedRpProfile || $selection.selectedRpProfile === EMPTY_SELECTION) {
      engine.error = translateNow("session.noProfile");
      return;
    }

    loading = true;
    engine.error = "";
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
      engine.error = caught instanceof Error ? caught.message : translateNow("session.createSessionError");
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
    engine.messages = payload.log || [];
    logPagination = payload.pagination || {};
    sessionMetadata = payload.metadata || {};
    sessionNoteDraft = metadataSessionNote(sessionMetadata);
    sceneNoteDraft = typeof sessionMetadata.scene_note === "string" ? sessionMetadata.scene_note : "";
    selection.applyMetadata(payload.metadata || {});
  }

  async function loadOlderLog() {
    if (!route.scenarioId || !currentSessionId || loadingOlderLog || engine.sending || !logPagination.has_more_before) {
      return;
    }
    loadingOlderLog = true;
    engine.error = "";
    const previousHeight = chatLogElement?.scrollHeight || 0;
    try {
      const payload = await getSessionLog(route.scenarioId, currentSessionId, {
        turnLimit: LOG_TURN_PAGE_SIZE,
        beforeTurn: logPagination.min_turn
      });
      engine.messages = mergeOlderLogMessages(engine.messages, payload.log || []);
      logPagination = mergeLogPagination(logPagination, payload.pagination || {});
      await tick();
      if (chatLogElement) {
        chatLogElement.scrollTop = chatLogElement.scrollHeight - previousHeight;
      }
    } catch (caught) {
      engine.error = caught instanceof Error ? caught.message : translateNow("session.loadOlderError");
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
    sessionState = payload.state || {};
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

  onDestroy(() => engine.dispose());

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

  const latestTurn = $derived(engine.messages.length
    ? Math.max(...engine.messages.filter((m) => m.turn != null).map((m) => /** @type {number} */ (m.turn)))
    : -1);

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
    engine.input = preset;
    engine.turnNotice = translateNow("session.editBranchNotice");
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

  /** @param {'quote' | 'asterisk'} mode */
  async function wrapSelection(mode) {
    if (!composer) {
      return;
    }
    const start = composer.selectionStart;
    const end = composer.selectionEnd;
    const wrapped = wrapComposerSelection(engine.input, start, end, mode);
    engine.input = wrapped.value;
    await tick();
    composer.focus();
    composer.setSelectionRange(wrapped.cursor, wrapped.cursor);
  }

  /** @param {KeyboardEvent} event */
  function handleKeydown(event) {
    if (engine.sending || !currentSessionId) return;
    if (!shouldSubmitComposer(event, $preferences.sendOnEnter)) return;
    event.preventDefault();
    if (engine.input.trim()) void submitTurn();
  }

  function adjustTextareaHeight() {
    if (composer) {
      composer.style.height = "auto";
      composer.style.height = Math.max(48, composer.scrollHeight) + "px";
    }
  }

  $effect(() => {
    if (engine.input !== undefined) {
      tick().then(adjustTextareaHeight);
    }
  });

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
    return JSON.stringify(sessionState || {}, null, 2);
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
    return Object.keys(sessionState || {}).slice(0, 10);
  }

  /** @param {string} sessionId */
  async function copyBranchSessionId(sessionId) {
    try {
      await navigator.clipboard?.writeText(sessionId);
      engine.turnNotice = translateNow("session.sessionIdCopied", { sessionId });
    } catch {
      engine.turnNotice = `Session ID: ${sessionId}`;
    }
  }

  /** @param {Record<string, any>} branch */
  async function renameBranchSession(branch) {
    if (!route.scenarioId || !branch?.session_id || engine.sending) return;
    const currentName = branch.display_name || branch.session_id;
    const nextName = window.prompt("Branch name", currentName);
    if (nextName === null) return;
    const trimmed = nextName.trim();
    if (!trimmed || trimmed === currentName) return;
    try {
      await updateSessionSettings(route.scenarioId, branch.session_id, { display_name: trimmed });
      await loadTimeline(route.scenarioId, currentSessionId);
      engine.turnNotice = translateNow("session.branchNameUpdated", { name: trimmed });
    } catch (caught) {
      engine.error = caught instanceof Error ? caught.message : translateNow("session.branchNameUpdateError");
    }
  }

  function lastUpdatedAt() {
    return sessionMetadata.updated_at || sessionMetadata.created_at || translateNow("common.unrecorded");
  }

  /** @param {"prev" | "next"} direction */
  async function switchStarting(direction) {
    if (!route.scenarioId || !currentSessionId || switchingStarting || startings.length <= 1) return;
    const currentStarting = engine.messages.find((/** @type {any} */ m) => m.is_starting);
    const currentId = currentStarting?.starting_id || startings[0]?.id;
    const currentIndex = startings.findIndex((/** @type {any} */ s) => s.id === currentId);
    const next = (currentIndex + (direction === "next" ? 1 : -1) + startings.length) % startings.length;
    switchingStarting = true;
    try {
      await updateSessionStarting(route.scenarioId, currentSessionId, startings[next].id);
      await reloadSession(route.scenarioId, currentSessionId);
    } catch (caught) {
      engine.error = caught instanceof Error ? caught.message : translateNow("session.switchStartingError");
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
    <SessionSidebar
      {layout}
      {selection}
      scenarioId={route.scenarioId || ""}
      {currentSessionId}
      {startings}
      bind:selectedStartingId
      {loading}
      {openPicker}
      {createSelectedSession}
    />
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

    {#if engine.error}
      <p class="notice error-notice">{engine.error}</p>
    {/if}
    {#if engine.turnNotice}
      <p class="notice">{engine.turnNotice}</p>
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
        <ChatPanel
          scenarioId={route.scenarioId || ""}
          {isMobile}
          {layout}
          {preferences}
          {openSessionInfo}
          {openSessionSettings}
          bind:chatLogElement
          {handleChatLogScroll}
          messages={engine.messages}
          {logPagination}
          {loadingOlderLog}
          sending={engine.sending}
          {loadOlderLog}
          {loadLatestLog}
          logTurnPageSize={LOG_TURN_PAGE_SIZE}
          {userLabel}
          {latestTurn}
          {resolveUser}
          {displaySegments}
          {expandedMetaSegments}
          {metaSegmentKey}
          {toggleMetaSegment}
          {editMessageTurn}
          {editMessageRole}
          bind:editDraft
          {editSaving}
          {cancelEditing}
          {saveEdit}
          {shouldBranchFromEditedUserMessage}
          {startEditing}
          {startings}
          {sessionMetadata}
          {switchingStarting}
          {switchStarting}
          {handleContinue}
          {handleRegenerate}
          {handleDeleteMessage}
          {deletingTurn}
          {openBranchDialog}
          {handleSwitchCandidate}
          turnJobPolling={engine.turnJobPolling}
          stateUpdating={engine.stateUpdating}
          newMessageBadge={engine.newMessageBadge}
          {dismissNewMessageBadge}
          {submitTurn}
          bind:composer
          bind:input={engine.input}
          {currentSessionId}
          {handleKeydown}
          {wrapSelection}
          stopGeneration={engine.stopGeneration}
        />

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
            <StatePanel state={sessionState} scenarioId={route.scenarioId || ""} stateJsonStr={stateJson()} />
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
                <div><dt>Turns</dt><dd>{sessionMetadata.turn_count ?? engine.messages.length}</dd></div>
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
                <div><dt>Log entries</dt><dd>{engine.messages.length}</dd></div>
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

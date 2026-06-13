<script>
  import { ArrowDown, ArrowUp, Copy, Plus, RotateCcw, Save, Trash2, X } from "lucide-svelte";
  import { Background, BackgroundVariant, Controls, SvelteFlow } from "@xyflow/svelte";
  import "@xyflow/svelte/dist/style.css";
  import {
    getScenarioPromptPreview,
    getScenarioPromptGraph,
    getScenarioSettings,
    getStartManifest,
    getStartPromptGraph,
    listScenarioStarts,
    updateScenarioSettings,
    updateScenarioPromptGraph,
    updateStartManifest,
    updateStartPromptGraph
  } from "../api.js";
  import { t, translateNow } from "../i18n.js";
  import {
    RAG_SOURCE_OPTIONS,
    RAG_TYPE_BUDGET_KEYS,
    RAG_TYPE_LIMIT_KEYS,
    buildPromptFlowEdges,
    buildPromptFlowNodes,
    budgetEnabled,
    deletePromptNodeFromGraph,
    defaultRoleForType,
    duplicatePromptNodeInGraph,
    graphWithNormalizedOrder,
    movePromptNode,
    nodeTypeBadge,
    nodeTypeCssClass,
    normalizeNodeForType,
    normalizedRagSources,
    parseOptionalNumber,
    promptOrderDuplicateWarnings,
    renamePromptNodeInGraph,
    reorderPromptNodeByDrop,
    setBudgetEnabled,
    setOptionalNumberField,
    setRagSource,
    setRagTypeBudget,
    setRagTypeLimit,
    sortPromptNodes
  } from "../promptGraphEditor.js";
  import PromptNodeList from "../PromptNodeList.svelte";
  import PromptPreviewPanel from "../PromptPreviewPanel.svelte";

  /** @type {{
   *   scenarioId?: string,
   *   hidden?: boolean,
   *   files?: Array<{ path: string, size?: number }>,
   *   sessions?: Array<Record<string, any>>,
   *   personas?: Array<Record<string, any>>,
   *   profiles?: Array<Record<string, any>>,
   *   loadingPreviewChoices?: boolean,
   *   isMobile?: boolean,
   *   promptPreviewError?: string,
   *   previewSessionId?: string,
   *   previewPersonaId?: string,
   *   previewProfileId?: string,
   *   previewUserMessage?: string,
   * }} */
  let {
    scenarioId = "",
    hidden = false,
    files = [],
    sessions = [],
    personas = [],
    profiles = [],
    loadingPreviewChoices = false,
    isMobile = false,
    // Bound to the page: also set when loading preview choices fails there.
    promptPreviewError = $bindable(""),
    previewSessionId = $bindable(""),
    previewPersonaId = $bindable(""),
    previewProfileId = $bindable(""),
    previewUserMessage = $bindable("")
  } = $props();

  let loadingPromptGraph = $state(false);
  let loadingPromptPreview = $state(false);
  let savingPromptGraph = $state(false);
  let promptGraphError = $state("");
  let promptGraphMessage = $state("");
  /** @type {"panels" | "visual"} */
  let promptView = $state("panels");
  let promptGraph = $state(/** @type {Record<string, any> | null} */ (null));
  let promptGraphSource = $state("");
  let promptGraphDirty = $state(false);
  let promptPreview = $state(/** @type {Record<string, any> | null} */ (null));
  let selectedVisualNodeId = $state("");
  /** @type {Array<string>} */
  let promptGraphWarnings = $state([]);
  const promptRoles = ["system", "user", "assistant", "messages"];
  const promptNodeTypes = [
    "file",
    "selected_persona",
    "state",
    "rag",
    "active_mods",
    "pinned_characters",
    "session_log",
    "user_note",
    "scene_note",
    "current_user_message",
    "condition",
    "output"
  ];
  let addingNode = $state(false);
  let newNodeId = $state("");
  let newNodeType = $state("file");
  let newNodeRole = $state("system");
  let newNodePath = $state("");
  let newNodeRequired = $state(false);
  let newNodeError = $state("");
  let draggedNodeId = $state("");
  let dragTargetNodeId = $state("");
  let dragDropAfter = $state(false);

  /** @type {Array<Record<string, any>>} */
  let starts = $state([]);
  let startsLoading = $state(false);
  let startsError = $state("");
  /** @type {{ prompt_graph_mode: string }} */
  let scenarioSettings = $state({ prompt_graph_mode: "common" });
  let savingSettings = $state(false);
  let settingsMessage = $state("");
  let settingsError = $state("");
  /** Currently selected start tab in per_start mode */
  let selectedStartTabId = $state("");
  /** Whether the current promptGraph belongs to a specific start (per_start mode) */
  let activeStartId = $state("");
  /** true when the loaded graph is the start's own (not inherited) */
  let currentGraphOwnFlag = $state(true);
  /** PG-2: duplicate-to-start modal */
  let duplicateGraphModal = $state(false);
  let duplicateGraphTargetId = $state("");
  let duplicatingGraph = $state(false);
  let duplicateGraphMessage = $state("");
  let duplicateGraphError = $state("");

  let manifestModalOpen = $state(false);
  let manifestModalStartId = $state("");
  let manifestName = $state("");
  let manifestDescription = $state("");
  let manifestLoreInclude = $state("");
  let manifestLoreExclude = $state("");
  let manifestInitialState = $state("");
  let savingManifest = $state(false);
  let manifestMessage = $state("");
  let manifestError = $state("");

  const promptNodeList = $derived(sortPromptNodes(/** @type {Array<Record<string, any>>} */ (promptGraph?.nodes || [])));
  const selectedPromptNodeIndex = $derived(promptNodeList.findIndex((node) => node.id === selectedVisualNodeId));
  const selectedPromptNode = $derived(selectedPromptNodeIndex >= 0 ? promptNodeList[selectedPromptNodeIndex] : null);
  const visualFlowNodes = $derived(buildPromptFlowNodes(promptNodeList));
  const visualFlowEdges = $derived(buildPromptFlowEdges(promptNodeList, /** @type {Array<Record<string, any>>} */ (promptGraph?.edges || []), selectedVisualNodeId));
  const promptGraphLocalWarnings = $derived(promptOrderDuplicateWarnings(promptNodeList));
  const visiblePromptGraphWarnings = $derived([...promptGraphWarnings, ...promptGraphLocalWarnings]);

  async function loadPromptGraph() {
    if (!scenarioId) {
      return;
    }
    loadingPromptGraph = true;
    promptGraphError = "";
    try {
      const payload = await getScenarioPromptGraph(scenarioId);
      promptGraph = payload.graph || null;
      promptGraphSource = payload.source || "";
      promptGraphWarnings = payload.warnings || [];
      promptGraphDirty = false;
      promptGraphMessage = "";
      activeStartId = "";
      currentGraphOwnFlag = true;
      selectedVisualNodeId = sortPromptNodes(/** @type {Array<Record<string, any>>} */ (promptGraph?.nodes || []))[0]?.id || "";
    } catch (caught) {
      promptGraphError = caught instanceof Error ? caught.message : translateNow("editor.loadGraphError");
      promptGraph = null;
      promptGraphSource = "";
      promptGraphWarnings = [];
      selectedVisualNodeId = "";
    } finally {
      loadingPromptGraph = false;
    }
  }

  export async function loadPromptWorkspace() {
    const settings = await loadScenarioSettings();
    if (settings.prompt_graph_mode !== "per_start") {
      selectedStartTabId = "";
      await loadPromptGraph();
      return;
    }

    await loadStarts();
    const startId = selectedStartTabId || starts[0]?.id || "";
    selectedStartTabId = startId;
    if (startId) {
      await loadStartPromptGraph(startId);
    } else {
      promptGraph = null;
      activeStartId = "";
      selectedVisualNodeId = "";
    }
  }

  /** @returns {Array<Record<string, any>>} */
  function promptNodes() {
    return promptNodeList;
  }

  function markPromptGraphDirty() {
    promptGraphDirty = true;
    promptGraphMessage = "";
  }

  /**
   * @param {number} index
   * @param {string} field
   * @param {unknown} value
   */
  function updateNodeField(index, field, value) {
    if (!promptGraph) return;
    const nodes = [...promptNodeList];
    const current = nodes[index] || {};
    if (value === undefined) {
      const next = { ...current };
      delete next[field];
      nodes[index] = next;
    } else {
      nodes[index] = { ...current, [field]: value };
    }
    promptGraph = { ...promptGraph, nodes: field === "order" ? sortPromptNodes(nodes) : nodes };
    markPromptGraphDirty();
  }

  /**
   * @param {number} index
   * @param {string} value
   */
  function updateNodeOrder(index, value) {
    const trimmed = value.trim();
    if (!trimmed) {
      updateNodeField(index, "order", undefined);
      return;
    }
    const order = Number(trimmed);
    if (!Number.isFinite(order)) {
      return;
    }
    updateNodeField(index, "order", order);
  }

  /**
   * @param {number} index
   * @param {Record<string, any>} nextNode
   */
  function updateNode(index, nextNode) {
    if (!promptGraph) return;
    const nodes = [...promptNodeList];
    nodes[index] = nextNode;
    promptGraph = { ...promptGraph, nodes: sortPromptNodes(nodes) };
    markPromptGraphDirty();
  }

  /**
   * @param {number} index
   * @param {"up" | "down"} direction
   */
  function moveNode(index, direction) {
    if (!promptGraph) return;
    const reordered = movePromptNode(promptNodeList, index, direction);
    if (!reordered) return;
    promptGraph = { ...promptGraph, nodes: reordered };
    markPromptGraphDirty();
  }

  /**
   * @param {string} value
   * @returns {number | undefined}
   */
  function optionalNumber(value) {
    return parseOptionalNumber(value);
  }

  async function savePromptGraph() {
    if (!scenarioId || !promptGraph || savingPromptGraph) return;
    savingPromptGraph = true;
    promptGraphError = "";
    promptGraphMessage = "";
    try {
      const normalizedGraph = graphWithNormalizedOrder(promptGraph);
      const payload = await updateScenarioPromptGraph(scenarioId, normalizedGraph);
      promptGraph = payload.graph || null;
      promptGraphSource = payload.source || "vault";
      promptGraphWarnings = payload.warnings || [];
      promptGraphDirty = false;
      promptGraphMessage = translateNow("editor.graphSaved");
    } catch (caught) {
      promptGraphError = caught instanceof Error ? caught.message : translateNow("editor.saveGraphError");
    } finally {
      savingPromptGraph = false;
    }
  }

  function roleplayProfiles() {
    return profiles.filter((profile) => profile.kind === "roleplay");
  }

  /** @param {Record<string, any>} node */
  function fileNodePathOptions(node) {
    const paths = files.map((file) => file.path);
    if (typeof node.path === "string" && node.path && !paths.includes(node.path)) {
      paths.unshift(node.path);
    }
    return paths;
  }

  /** @param {Record<string, any>} node */
  function conditionMode(node) {
    if (node.condition?.["scenario.image_enabled"] === true) {
      return "image_enabled";
    }
    if (node.condition?.["scenario.image_enabled"] === false) {
      return "image_disabled";
    }
    return "none";
  }

  /**
   * @param {number} index
   * @param {Record<string, any>} node
   * @param {string} mode
   */
  function updateCondition(index, node, mode) {
    const nextNode = { ...node };
    if (mode === "image_enabled") {
      nextNode.condition = { "scenario.image_enabled": true };
    } else if (mode === "image_disabled") {
      nextNode.condition = { "scenario.image_enabled": false };
    } else {
      delete nextNode.condition;
    }
    updateNode(index, nextNode);
  }

  async function runPromptPreview() {
    if (!scenarioId || !previewUserMessage.trim() || loadingPromptPreview) {
      return;
    }
    loadingPromptPreview = true;
    promptPreviewError = "";
    try {
      promptPreview = await getScenarioPromptPreview(scenarioId, {
        session_id: previewSessionId,
        persona_id: previewSessionId ? "" : previewPersonaId,
        profile_id: previewSessionId ? "" : previewProfileId,
        starting_id: !previewSessionId && scenarioSettings.prompt_graph_mode === "per_start" ? activeStartId : "",
        user_message: previewUserMessage
      });
    } catch (caught) {
      promptPreviewError = caught instanceof Error ? caught.message : translateNow("editor.previewError");
      promptPreview = null;
    } finally {
      loadingPromptPreview = false;
    }
  }

  /**
   * @param {Record<string, any>} node
   * @param {string} key
   */
  function ragTypeBudgetValue(node, key) {
    const value = node?.token_budgets?.[key];
    return typeof value === "number" && Number.isFinite(value) ? value : "";
  }

  /**
   * @param {Record<string, any>} node
   * @param {string} key
   */
  function ragTypeLimitValue(node, key) {
    const value = node?.limits?.[key];
    return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : "";
  }

  /**
   * @param {Record<string, any>} node
   * @param {string} source
   */
  function ragSourceChecked(node, source) {
    return normalizedRagSources(node).includes(source);
  }

  /** @param {string} nodeId */
  function selectVisualNode(nodeId) {
    selectedVisualNodeId = nodeId === "final_prompt" ? "" : nodeId;
  }

  /** @param {string} nodeId */
  function selectPromptNodeFromList(nodeId) {
    addingNode = false;
    selectVisualNode(nodeId);
  }

  function openAddPromptNodeForm() {
    selectVisualNode("");
    addingNode = true;
    newNodeError = "";
  }

  function clearNodeDragState() {
    document.removeEventListener("pointermove", updateNodeDragFromPointer);
    document.removeEventListener("pointerup", finishNodePointerDrag);
    document.removeEventListener("pointercancel", clearNodeDragState);
    draggedNodeId = "";
    dragTargetNodeId = "";
    dragDropAfter = false;
  }

  /**
   * @param {string} nodeId
   * @param {PointerEvent} event
   */
  function startNodeDrag(nodeId, event) {
    event.preventDefault();
    event.stopPropagation();
    draggedNodeId = nodeId;
    dragTargetNodeId = "";
    dragDropAfter = false;
    document.addEventListener("pointermove", updateNodeDragFromPointer);
    document.addEventListener("pointerup", finishNodePointerDrag);
    document.addEventListener("pointercancel", clearNodeDragState);
  }

  /**
   * @param {PointerEvent} event
   */
  function updateNodeDragFromPointer(event) {
    if (!draggedNodeId) return;
    event.preventDefault();
    const element = document.elementFromPoint(event.clientX, event.clientY);
    const target = element?.closest?.(".node-item");
    if (!(target instanceof HTMLElement)) {
      dragTargetNodeId = "";
      return;
    }
    const nodeId = target.dataset.nodeId || "";
    if (!nodeId || nodeId === draggedNodeId) {
      dragTargetNodeId = "";
      return;
    }
    dragTargetNodeId = nodeId;
    const rect = target.getBoundingClientRect();
    const sourceIndex = promptNodes().findIndex((node) => node.id === draggedNodeId);
    const targetIndex = promptNodes().findIndex((node) => node.id === nodeId);
    const pointerAfter = event.clientY > rect.top + rect.height / 2;
    dragDropAfter = sourceIndex < targetIndex ? true : sourceIndex > targetIndex ? false : pointerAfter;
  }

  function finishNodePointerDrag() {
    const sourceNodeId = draggedNodeId;
    const targetNodeId = dragTargetNodeId;
    const insertAfter = dragDropAfter;
    if (targetNodeId) {
      reorderNodeByDrop(sourceNodeId, targetNodeId, insertAfter);
    }
    clearNodeDragState();
  }

  /**
   * @param {string} sourceNodeId
   * @param {string} targetNodeId
   * @param {boolean} insertAfter
   */
  function reorderNodeByDrop(sourceNodeId, targetNodeId, insertAfter) {
    if (!promptGraph || !sourceNodeId || !targetNodeId || sourceNodeId === targetNodeId) {
      return;
    }
    const reordered = reorderPromptNodeByDrop(promptNodeList, sourceNodeId, targetNodeId, insertAfter);
    if (!reordered) {
      return;
    }
    promptGraph = { ...promptGraph, nodes: reordered.nodes };
    selectedVisualNodeId = reordered.movedId;
    addingNode = false;
    markPromptGraphDirty();
  }

  /** @param {number} index */
  function deleteNode(index) {
    if (!promptGraph) return;
    const nextGraph = deletePromptNodeFromGraph(promptGraph, promptNodeList, index);
    if (!nextGraph) return;
    promptGraph = nextGraph;
    selectedVisualNodeId = "";
    markPromptGraphDirty();
  }

  /** @param {number} index */
  function requestDeleteNode(index) {
    const node = promptNodes()[index];
    if (!node) return;
    if (!window.confirm(translateNow("editor.deleteNodeConfirm", { id: node.id }))) return;
    deleteNode(index);
  }

  /** @param {number} index */
  function duplicateNode(index) {
    if (!promptGraph) return;
    const duplicated = duplicatePromptNodeInGraph(promptGraph, promptNodeList, index);
    if (!duplicated) return;
    promptGraph = duplicated.graph;
    selectedVisualNodeId = duplicated.id;
    markPromptGraphDirty();
  }

  function promptNodeFallbackPath() {
    return files[0]?.path || "scenario.md";
  }

  /**
   * @param {number} index
   * @param {string} newId
   * @returns {string} error message or ""
   */
  function renameNode(index, newId) {
    const id = newId.trim();
    if (!id) return translateNow("editor.idRequired");
    if (!/^[a-z0-9_]+$/.test(id)) return translateNow("editor.idInvalid");
    const nodes = promptNodes();
    if (nodes.some((n, i) => i !== index && n.id === id)) return translateNow("editor.idExists", { id });
    if (!promptGraph) return "";
    const nextGraph = renamePromptNodeInGraph(promptGraph, nodes, index, id);
    if (!nextGraph) return "";
    promptGraph = nextGraph;
    selectedVisualNodeId = id;
    markPromptGraphDirty();
    return "";
  }

  /**
   * @param {number} index
   * @param {Record<string, any>} node
   * @param {string} newType
   */
  function changeNodeType(index, node, newType) {
    updateNode(index, normalizeNodeForType({ ...node, role: defaultRoleForType(newType) }, newType, promptNodeFallbackPath()));
  }

  function submitAddNode() {
    newNodeError = "";
    const id = newNodeId.trim();
    if (!id) { newNodeError = translateNow("editor.idRequired"); return; }
    if (!/^[a-z0-9_]+$/.test(id)) { newNodeError = translateNow("editor.idInvalid"); return; }
    if (promptNodes().some((n) => n.id === id)) { newNodeError = translateNow("editor.idExists", { id }); return; }
    const maxOrder = promptNodes().reduce((max, n) => Math.max(max, n.order ?? 0), 0);
    /** @type {Record<string, any>} */
    const newNode = normalizeNodeForType({
      id,
      type: newNodeType,
      role: newNodeRole,
      order: maxOrder + 10,
      required: newNodeRequired,
      ...(newNodeType === "file" ? { path: newNodePath || files[0]?.path || "scenario.md" } : {})
    }, newNodeType, promptNodeFallbackPath());
    const nodes = [...promptNodes(), newNode];
    promptGraph = { ...promptGraph, nodes };
    selectedVisualNodeId = id;
    addingNode = false;
    newNodeId = "";
    newNodeType = "file";
    newNodeRole = "system";
    newNodePath = "";
    newNodeRequired = false;
    markPromptGraphDirty();
  }

  /**
   * @param {number} index
   * @param {string} source
   * @param {boolean} enabled
   */
  function updateRagSource(index, source, enabled) {
    const node = promptNodes()[index];
    if (!node) return;
    updateNode(index, setRagSource(node, source, enabled));
  }

  /**
   * @param {number} index
   * @param {string} key
   * @param {string} value
   */
  function updateRagTypeBudget(index, key, value) {
    const node = promptNodes()[index];
    if (!node) return;
    updateNode(index, setRagTypeBudget(node, key, optionalNumber(value)));
  }

  /**
   * @param {number} index
   * @param {string} key
   * @param {string} value
   */
  function updateRagTypeLimit(index, key, value) {
    const node = promptNodes()[index];
    if (!node) return;
    updateNode(index, setRagTypeLimit(node, key, optionalNumber(value)));
  }

  /**
   * @param {number} index
   * @param {string} field
   * @param {string} value
   */
  function updateOptionalNumberField(index, field, value) {
    const node = promptNodes()[index];
    if (!node) return;
    updateNode(index, setOptionalNumberField(node, field, optionalNumber(value)));
  }

  /**
   * @param {number} index
   * @param {boolean} enabled
   */
  function updateBudgetEnabled(index, enabled) {
    const node = promptNodes()[index];
    if (!node) return;
    updateNode(index, setBudgetEnabled(node, enabled));
  }

  async function loadStarts() {
    if (!scenarioId) return;
    startsLoading = true;
    startsError = "";
    try {
      const payload = await listScenarioStarts(scenarioId);
      starts = payload.starts || [];
      if (scenarioSettings.prompt_graph_mode === "per_start" && !selectedStartTabId && starts.length) {
        selectedStartTabId = starts[0].id;
      }
    } catch (caught) {
      startsError = caught instanceof Error ? caught.message : translateNow("editor.startsError");
    } finally {
      startsLoading = false;
    }
  }

  async function loadScenarioSettings() {
    if (!scenarioId) return scenarioSettings;
    try {
      const payload = await getScenarioSettings(scenarioId);
      scenarioSettings = payload.settings || { prompt_graph_mode: "common" };
      return scenarioSettings;
    } catch {
      // non-fatal: keep defaults
      return scenarioSettings;
    }
  }

  async function saveScenarioSettings(newSettings = scenarioSettings) {
    if (!scenarioId || savingSettings) return scenarioSettings;
    savingSettings = true;
    settingsMessage = "";
    settingsError = "";
    try {
      const payload = await updateScenarioSettings(scenarioId, newSettings);
      scenarioSettings = payload.settings || newSettings;
      settingsMessage = translateNow("editor.saved");
      return scenarioSettings;
    } catch (caught) {
      settingsError = caught instanceof Error ? caught.message : translateNow("editor.saveGraphError");
      return scenarioSettings;
    } finally {
      savingSettings = false;
    }
  }

  function confirmDiscardPromptChanges() {
    return !promptGraphDirty || window.confirm(translateNow("editor.unsavedWarning"));
  }

  /** @param {boolean} enabled */
  async function setPromptGraphMode(enabled) {
    if (!confirmDiscardPromptChanges()) {
      return;
    }
    const mode = enabled ? "per_start" : "common";
    scenarioSettings = { ...scenarioSettings, prompt_graph_mode: mode };
    await saveScenarioSettings({ prompt_graph_mode: mode });
    if (scenarioSettings.prompt_graph_mode === "per_start") {
      await loadStarts();
      const startId = selectedStartTabId || starts[0]?.id || "";
      selectedStartTabId = startId;
      if (startId) {
        await loadStartPromptGraph(startId);
      }
      return;
    }
    selectedStartTabId = "";
    activeStartId = "";
    currentGraphOwnFlag = true;
    await loadPromptGraph();
  }

  /** @param {string} startId Load a start's prompt graph into the editor. */
  async function loadStartPromptGraph(startId) {
    if (!scenarioId) return;
    loadingPromptGraph = true;
    promptGraphError = "";
    try {
      const payload = await getStartPromptGraph(scenarioId, startId);
      promptGraph = payload.graph || null;
      promptGraphSource = payload.source || "start";
      promptGraphWarnings = payload.warnings || [];
      promptGraphDirty = false;
      promptGraphMessage = "";
      currentGraphOwnFlag = payload.own_graph ?? true;
      activeStartId = startId;
      selectedStartTabId = startId;
      selectedVisualNodeId = sortPromptNodes(/** @type {Array<Record<string, any>>} */ (promptGraph?.nodes || []))[0]?.id || "";
    } catch (caught) {
      promptGraphError = caught instanceof Error ? caught.message : translateNow("editor.loadGraphError");
      promptGraph = null;
    } finally {
      loadingPromptGraph = false;
    }
  }

  /** Save current graph. Routes to start-specific or scenario-level depending on mode. */
  async function savePromptGraphRouted() {
    if (!scenarioId || !promptGraph || savingPromptGraph) return;
    if (scenarioSettings.prompt_graph_mode === "per_start" && activeStartId) {
      savingPromptGraph = true;
      promptGraphError = "";
      promptGraphMessage = "";
      try {
        const normalizedGraph = graphWithNormalizedOrder(promptGraph);
        const payload = await updateStartPromptGraph(scenarioId, activeStartId, normalizedGraph);
        promptGraph = payload.graph || null;
        promptGraphSource = payload.source || "start";
        promptGraphWarnings = payload.warnings || [];
        promptGraphDirty = false;
        currentGraphOwnFlag = true;
        promptGraphMessage = translateNow("editor.graphSaved");
      } catch (caught) {
        promptGraphError = caught instanceof Error ? caught.message : translateNow("editor.saveGraphError");
      } finally {
        savingPromptGraph = false;
      }
    } else {
      await savePromptGraph();
    }
  }

  /** PG-2: duplicate current scenario graph to a start's directory. */
  async function duplicateGraphToStart() {
    if (!scenarioId || !promptGraph || !duplicateGraphTargetId || duplicatingGraph) return;
    duplicatingGraph = true;
    duplicateGraphMessage = "";
    duplicateGraphError = "";
    try {
      const graphToCopy = { ...promptGraph, id: duplicateGraphTargetId };
      await updateStartPromptGraph(scenarioId, duplicateGraphTargetId, graphToCopy);
      duplicateGraphMessage = translateNow("editor.duplicateGraphDone", { id: duplicateGraphTargetId });
    } catch (caught) {
      duplicateGraphError = caught instanceof Error ? caught.message : translateNow("editor.saveGraphError");
    } finally {
      duplicatingGraph = false;
    }
  }

  /** @param {string} startId */
  async function switchStartTab(startId) {
    if (startId === activeStartId && promptGraph) return;
    if (!confirmDiscardPromptChanges()) return;
    selectedStartTabId = startId;
    await loadStartPromptGraph(startId);
  }

  /** @param {string} startId */
  async function openManifestModal(startId) {
    if (!scenarioId) return;
    manifestModalStartId = startId;
    manifestMessage = "";
    manifestError = "";
    manifestName = "";
    manifestDescription = "";
    manifestLoreInclude = "";
    manifestLoreExclude = "";
    manifestInitialState = "";
    try {
      const payload = await getStartManifest(scenarioId, startId);
      const m = payload.manifest || {};
      manifestName = m.name || "";
      manifestDescription = m.description || "";
      manifestLoreInclude = (m.lore_include || []).join(", ");
      manifestLoreExclude = (m.lore_exclude || []).join(", ");
      manifestInitialState = m.initial_state_path || "";
    } catch {
      // manifest が存在しない場合は空フォームで新規作成
    }
    manifestModalOpen = true;
  }

  async function saveManifest() {
    if (!scenarioId || !manifestModalStartId || savingManifest) return;
    savingManifest = true;
    manifestMessage = "";
    manifestError = "";
    const parseIds = (/** @type {string} */ raw) =>
      raw.split(",").map((s) => s.trim()).filter(Boolean);
    try {
      await updateStartManifest(scenarioId, manifestModalStartId, {
        name: manifestName.trim(),
        description: manifestDescription.trim(),
        lore_include: parseIds(manifestLoreInclude),
        lore_exclude: parseIds(manifestLoreExclude),
        initial_state_path: manifestInitialState.trim() || null,
      });
      manifestMessage = translateNow("editor.saved");
      await loadStarts();
    } catch (caught) {
      manifestError = caught instanceof Error ? caught.message : translateNow("editor.saveGraphError");
    } finally {
      savingManifest = false;
    }
  }
  /** Tab bar hook: load starts on first prompt-tab activation. */
  export function ensureStartsLoaded() {
    if (!starts.length) void loadStarts();
  }

  /** Called by the page after a starting source file was created. @param {string} createdId */
  export async function handleStartCreated(createdId) {
    await loadStarts();
    if (scenarioSettings.prompt_graph_mode === "per_start") {
      selectedStartTabId = createdId;
      await loadStartPromptGraph(createdId);
    }
  }

  /** Called by the page after a source file was deleted. @param {boolean} isStart */
  export async function handleSourceDeleted(isStart) {
    if (isStart) {
      await loadStarts();
      if (scenarioSettings.prompt_graph_mode === "per_start") {
        const nextStartId = starts.find((start) => start.id === selectedStartTabId)?.id || starts[0]?.id || "";
        selectedStartTabId = nextStartId;
        if (nextStartId) {
          await loadStartPromptGraph(nextStartId);
        } else {
          promptGraph = null;
          activeStartId = "";
          selectedVisualNodeId = "";
        }
      } else {
        await loadPromptGraph();
      }
    } else {
      await loadPromptGraph();
    }
  }
</script>

<div class="prompt-tab-content" style:display={hidden ? "none" : null}>
  <div class="prompt-actions-bar">
    {#if promptGraph}
      <div class="prompt-graph-meta-compact">
        <span>graph: {promptGraph.id}</span>
        <span>v{promptGraph.version}</span>
        {#if scenarioSettings.prompt_graph_mode === "per_start" && !currentGraphOwnFlag}
          <span class="graph-inherited-notice">{$t("editor.graphInherited")}</span>
        {/if}
        {#if promptGraphDirty}
          <span class="dirty-badge">未保存</span>
        {/if}
        {#if scenarioSettings.prompt_graph_mode === "per_start" && activeStartId}
          <button class="meta-inline-button" type="button" onclick={() => void openManifestModal(activeStartId)}>
            manifest
          </button>
        {/if}
      </div>
    {/if}
    <label class="inline-check per-start-toggle">
      <input
        type="checkbox"
        checked={scenarioSettings.prompt_graph_mode === "per_start"}
        onchange={(e) => void setPromptGraphMode(e.currentTarget.checked)}
      />
      <span>{$t("editor.perStartMode")}</span>
    </label>
    {#if settingsMessage}<span class="mini-ok">{settingsMessage}</span>{/if}
    {#if settingsError}<span class="mini-error">{settingsError}</span>{/if}
    {#if promptGraph}
      <button type="button" disabled={savingPromptGraph} onclick={() => scenarioSettings.prompt_graph_mode === "per_start" && activeStartId ? void loadStartPromptGraph(activeStartId) : void loadPromptGraph()}>
        <RotateCcw size={15} aria-hidden="true" /> {$t("editor.reload")}
      </button>
      <button type="button" disabled={savingPromptGraph || !promptGraphDirty} onclick={() => void savePromptGraphRouted()}>
        <Save size={15} aria-hidden="true" /> {savingPromptGraph ? $t("editor.saving") : $t("editor.save")}
      </button>
      {#if starts.length && scenarioSettings.prompt_graph_mode === "common"}
        <button type="button" disabled={duplicatingGraph} onclick={() => { duplicateGraphModal = true; duplicateGraphTargetId = starts[0]?.id || ""; duplicateGraphMessage = ""; duplicateGraphError = ""; }}>
          <Copy size={15} aria-hidden="true" /> {$t("editor.duplicateGraph")}
        </button>
      {/if}
      {#if promptGraphMessage}
        <span>{promptGraphMessage}</span>
      {/if}
      <div class="meta-view-toggle">
        <button class:selected={promptView === "panels"} type="button" onclick={() => (promptView = "panels")}>
          {$t("editor.viewPanels")}
        </button>
        <button class:selected={promptView === "visual"} type="button" onclick={() => (promptView = "visual")}>
          {$t("editor.viewVisual")}
        </button>
      </div>
    {/if}
  </div>

  {#if scenarioSettings.prompt_graph_mode === "per_start" && starts.length}
    <div class="starts-tab-bar">
      {#each starts as start}
        <button
          class:selected={selectedStartTabId === start.id}
          type="button"
          onclick={() => void switchStartTab(start.id)}
        >
          {start.name || start.id}
          <span
            class="manifest-badge {start.has_manifest ? 'badge-on' : 'badge-off'}"
            title={start.has_manifest ? $t("editor.startHasManifest") : $t("editor.startNoManifest")}
          >{start.has_manifest ? "✓" : "!"}</span>
        </button>
      {/each}
    </div>
  {/if}

  {#if scenarioSettings.prompt_graph_mode === "per_start" && !selectedStartTabId}
    <p class="notice">{$t("editor.selectStartTab")}</p>
  {:else if loadingPromptGraph}
    <p class="notice">{$t("editor.loadingGraph")}</p>
  {:else if promptGraphError}
    <p class="notice error-notice">{promptGraphError}</p>
  {:else if promptGraph}

    {#if visiblePromptGraphWarnings.length}
      <div class="notice">
        {#each visiblePromptGraphWarnings as warning}
          <div>{warning}</div>
        {/each}
      </div>
    {/if}

    {#if promptView === "panels"}
      <div class="prompt-3pane">
        <PromptNodeList
          nodes={promptNodeList}
          selectedNodeId={selectedVisualNodeId}
          {draggedNodeId}
          {dragTargetNodeId}
          {dragDropAfter}
          selectNode={selectPromptNodeFromList}
          {startNodeDrag}
          addNode={openAddPromptNodeForm}
        />

        <!-- Middle: detail editor -->
        <div class="detail-pane">
          <div class="detail-pane-header">
            <h4>
              {#if selectedPromptNode && !addingNode}
                <span class="type-badge {nodeTypeCssClass(selectedPromptNode.type || '')}">{nodeTypeBadge(selectedPromptNode.type || '')}</span>
              {/if}
              {selectedPromptNode?.id || (addingNode ? $t("editor.newNode") : $t("editor.noSelection"))}
            </h4>
            {#if selectedPromptNode && !addingNode}
              <div class="detail-pane-actions">
                <button
                  class="icon-button"
                  type="button"
                  title={$t("editor.duplicateNode")}
                  onclick={() => duplicateNode(selectedPromptNodeIndex)}
                >
                  <Copy size={15} aria-hidden="true" />
                </button>
                <button
                  class="icon-button"
                  type="button"
                  title={$t("editor.deleteNode")}
                  onclick={() => requestDeleteNode(selectedPromptNodeIndex)}
                >
                  <Trash2 size={15} aria-hidden="true" />
                </button>
              </div>
            {/if}
          </div>

          {#key selectedVisualNodeId}
          <div class="detail-scroll">
            {#if addingNode}
              <div class="detail-section">
                <div class="section-label">新規ノード</div>
                <div class="field-row">
                  <span class="field-label">ID</span>
                  <div class="field-val"><input class="compact-input" type="text" bind:value={newNodeId} placeholder="node_id" /></div>
                </div>
                <div class="field-row">
                  <span class="field-label">Type</span>
                  <div class="field-val">
                    <select class="compact-input" bind:value={newNodeType}
                      onchange={() => { newNodeRole = defaultRoleForType(newNodeType); }}>
                      {#each promptNodeTypes as t}<option value={t}>{t}</option>{/each}
                    </select>
                  </div>
                </div>
                <div class="field-row">
                  <span class="field-label">Role</span>
                  <div class="field-val">
                    <select class="compact-input" bind:value={newNodeRole}>
                      {#each promptRoles as r}<option value={r}>{r}</option>{/each}
                    </select>
                  </div>
                </div>
                {#if newNodeType === "file"}
                  <div class="field-row">
                    <span class="field-label">Path</span>
                    <div class="field-val">
                      <select class="compact-input" bind:value={newNodePath}>
                        {#each files.map((f) => f.path) as p}<option value={p}>{p}</option>{/each}
                      </select>
                    </div>
                  </div>
                {/if}
                <div class="field-row">
                  <span class="field-label">Required</span>
                  <div class="field-val"><label class="inline-check"><input type="checkbox" bind:checked={newNodeRequired} /><span>必須ノード</span></label></div>
                </div>
                {#if newNodeError}
                  <p class="mini-error">{newNodeError}</p>
                {/if}
                <div class="field-row">
                  <div class="field-val" style="display:flex;gap:6px;">
                    <button type="button" class="primary-button" onclick={submitAddNode}>{$t("editor.add")}</button>
                    <button type="button" onclick={() => { addingNode = false; newNodeError = ""; }}>{$t("common.cancel")}</button>
                  </div>
                </div>
              </div>
            {:else if selectedPromptNode}
              {@const node = selectedPromptNode}
              {@const idx = selectedPromptNodeIndex}
              <div class="detail-section">
                <div class="section-label">基本設定</div>
                <div class="field-row">
                  <span class="field-label">ID</span>
                  <div class="field-val">
                    <input
                      class="compact-input"
                      type="text"
                      value={node?.id}
                      onchange={(e) => {
                        const err = renameNode(idx, e.currentTarget.value);
                        if (err) { e.currentTarget.value = node?.id ?? ""; e.currentTarget.setCustomValidity(err); e.currentTarget.reportValidity(); }
                        else { e.currentTarget.setCustomValidity(""); }
                      }}
                    />
                  </div>
                </div>
                <div class="field-row">
                  <span class="field-label">Type</span>
                  <div class="field-val">
                    <select class="compact-input" value={node?.type}
                      onchange={(e) => changeNodeType(idx, node ?? {}, e.currentTarget.value)}>
                      {#each promptNodeTypes as pt}<option value={pt}>{pt}</option>{/each}
                    </select>
                  </div>
                </div>
                <div class="field-row">
                  <span class="field-label">Role</span>
                  <div class="field-val">
                    <select class="compact-input" value={node?.role}
                      onchange={(e) => updateNodeField(idx, "role", e.currentTarget.value)}>
                      {#each promptRoles as r}<option value={r}>{r}</option>{/each}
                    </select>
                  </div>
                </div>
                <div class="field-row">
                  <span class="field-label">Order</span>
                  <div class="field-val">
                    <input
                      class="compact-input short"
                      type="number"
                      value={node?.order ?? ""}
                      onchange={(e) => updateNodeOrder(idx, e.currentTarget.value)}
                    />
                  </div>
                </div>
                <div class="field-row">
                  <span class="field-label">Required</span>
                  <div class="field-val">
                    <label class="inline-check"><input type="checkbox" checked={node?.required}
                      onchange={(e) => updateNodeField(idx, "required", e.currentTarget.checked)} /><span>必須ノード</span></label>
                  </div>
                </div>
                <div class="field-row">
                  <span class="field-label">Condition</span>
                  <div class="field-val">
                    <select class="compact-input" value={conditionMode(node || {})}
                      onchange={(e) => updateCondition(idx, node || {}, e.currentTarget.value)}>
                      <option value="none">{$t("editor.condNone")}</option>
                      <option value="image_enabled">{$t("editor.condImageOn")}</option>
                      <option value="image_disabled">{$t("editor.condImageOff")}</option>
                    </select>
                  </div>
                </div>
                {#if node?.type === "file"}
                  <div class="field-row">
                    <span class="field-label">Path</span>
                    <div class="field-val">
                      <select class="compact-input" value={node?.path || ""}
                        onchange={(e) => updateNodeField(idx, "path", e.currentTarget.value)}>
                        {#each fileNodePathOptions(node || {}) as p}<option value={p}>{p}</option>{/each}
                      </select>
                    </div>
                  </div>
                {/if}
              </div>

              {#if node?.type === "rag"}
                <div class="detail-section">
                  <div class="section-label">RAG ソース</div>
                  <div class="field-row">
                    <span class="field-label">Sources</span>
                    <div class="field-val rag-src-row">
                      {#each RAG_SOURCE_OPTIONS as source}
                        <label class="rag-src-item">
                          <input
                            type="checkbox"
                            checked={ragSourceChecked(node || {}, source)}
                            onchange={(e) => updateRagSource(idx, source, e.currentTarget.checked)}
                          />
                          {source}
                        </label>
                      {/each}
                    </div>
                  </div>
                  <div class="field-row">
                    <span class="field-label">件数上限</span>
                    <div class="field-val">
                      <input class="compact-input short" type="number" min="0" value={node?.limit ?? ""}
                        title={$t("editor.ragLimitHelp")}
                        oninput={(e) => updateOptionalNumberField(idx, "limit", e.currentTarget.value)} />
                    </div>
                  </div>
                  <div class="field-row">
                    <span class="field-label">件数上限(type別)</span>
                    <div class="field-val budget-3col">
                      {#each RAG_TYPE_LIMIT_KEYS as key}
                        <div>
                          <div class="budget-sub">{key}</div>
                          <input
                            class="compact-input"
                            type="number"
                            min="0"
                            step="1"
                            value={ragTypeLimitValue(node || {}, key)}
                            placeholder={key}
                            title={$t("editor.ragTypeLimitHelp")}
                            oninput={(e) => updateRagTypeLimit(idx, key, e.currentTarget.value)}
                          />
                        </div>
                      {/each}
                    </div>
                  </div>
                </div>
              {/if}

              {#if node?.type === "rag" || node?.type === "session_log"}
                <div class="detail-section">
                  <div class="section-label">Token Budget</div>
                  <div class="field-row">
                    <span class="field-label">Budget</span>
                    <div class="field-val">
                      <label class="inline-check">
                        <input
                          type="checkbox"
                          checked={budgetEnabled(node || {})}
                          onchange={(e) => updateBudgetEnabled(idx, e.currentTarget.checked)}
                        />
                        <span>有効</span>
                      </label>
                    </div>
                  </div>
                  {#if budgetEnabled(node || {})}
                    <div class="field-row">
                      <span class="field-label">合計上限</span>
                      <div class="field-val">
                        <input class="compact-input" type="number" min="0" value={node?.token_budget ?? ""}
                          oninput={(e) => updateOptionalNumberField(idx, "token_budget", e.currentTarget.value)} />
                      </div>
                    </div>
                    {#if node?.type === "rag"}
                      <div class="field-row">
                        <span class="field-label">Keyword上限</span>
                        <div class="field-val">
                          <input class="compact-input" type="number" min="0" value={node?.keyword_token_budget ?? ""}
                            title={$t("editor.ragKeywordBudgetHelp")}
                            oninput={(e) => updateOptionalNumberField(idx, "keyword_token_budget", e.currentTarget.value)} />
                        </div>
                      </div>
                      <div class="field-row">
                        <span class="field-label">type別</span>
                        <div class="field-val budget-3col">
                          {#each RAG_TYPE_BUDGET_KEYS as key}
                            <div>
                              <div class="budget-sub">{key}</div>
                              <input
                                class="compact-input"
                                type="number"
                                min="0"
                                value={ragTypeBudgetValue(node || {}, key)}
                                placeholder={key}
                                title={$t("editor.ragTypeBudgetHelp")}
                                oninput={(e) => updateRagTypeBudget(idx, key, e.currentTarget.value)}
                              />
                            </div>
                          {/each}
                        </div>
                      </div>
                    {/if}
                  {:else}
                    <p class="hint-copy">Budget disabled: retrieved content is not token-budgeted by this node.</p>
                  {/if}
                </div>
              {/if}
            {:else}
              <p class="notice">{$t("editor.nodeSelectHint")}</p>
            {/if}
          </div>
          {/key}

          {#if selectedPromptNode && !addingNode}
            {@const idx = selectedPromptNodeIndex}
            <div class="node-action-bar">
              <span class="editing-label">{selectedPromptNode.id} を編集中</span>
              <button
                type="button"
                disabled={idx <= 0}
                onclick={() => moveNode(idx, "up")}
              >
                <ArrowUp size={15} aria-hidden="true" /> {$t("editor.moveUp")}
              </button>
              <button
                type="button"
                disabled={idx >= promptNodeList.length - 1}
                onclick={() => moveNode(idx, "down")}
              >
                <ArrowDown size={15} aria-hidden="true" /> {$t("editor.moveDown")}
              </button>
            </div>
          {/if}
        </div>

        <!-- Right: preview -->
        <div class="preview-pane">
          <PromptPreviewPanel
            compact={true}
            {loadingPreviewChoices}
            {loadingPromptPreview}
            {promptPreviewError}
            {promptPreview}
            {sessions}
            {personas}
            bind:previewSessionId
            bind:previewPersonaId
            bind:previewProfileId
            bind:previewUserMessage
            {roleplayProfiles}
            {runPromptPreview}
          />
        </div>
      </div>
  {:else}
    {#if isMobile}
      <p class="notice">{$t("editor.visualDesktopOnly")}</p>
    {:else}
      <div class="visual-workspace" aria-label="Visual prompt flow">
        <div class="visual-canvas">
          <SvelteFlow
            nodes={visualFlowNodes}
            edges={visualFlowEdges}
            fitView
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable
            onnodeclick={({ node }) => selectVisualNode(node.id)}
          >
            <Controls />
            <Background variant={BackgroundVariant.Dots} />
          </SvelteFlow>
        </div>

        <aside class="visual-detail-panel">
          <div class="panel-header compact">
            <div>
              <p class="eyebrow">Node</p>
              <h4>{selectedPromptNode?.id || (addingNode ? $t("editor.newNode") : $t("editor.noSelection"))}</h4>
            </div>
            <div style="display:flex;gap:4px;align-items:center">
              {#if selectedPromptNode}
                <button
                  class="icon-button"
                  type="button"
                  title={$t("editor.duplicateNode")}
                  onclick={() => duplicateNode(selectedPromptNodeIndex)}
                >
                  <Copy size={15} aria-hidden="true" />
                </button>
                <button
                  class="icon-button"
                  type="button"
                  title={$t("editor.deleteNode")}
                  onclick={() => requestDeleteNode(selectedPromptNodeIndex)}
                >
                  <Trash2 size={15} aria-hidden="true" />
                </button>
              {/if}
              <button
                class="icon-button"
                type="button"
                title={$t("editor.addNode")}
                onclick={() => { addingNode = !addingNode; newNodeError = ""; }}
              >
                <Plus size={15} aria-hidden="true" />
              </button>
            </div>
          </div>

          {#if addingNode}
            <div class="visual-add-form">
              <label class="visual-field">
                <span class="visual-field-label">id</span>
                <input class="compact-input" type="text" bind:value={newNodeId} placeholder="node_id" />
              </label>
              <label class="visual-field">
                <span class="visual-field-label">type</span>
                <select class="compact-input" bind:value={newNodeType}
                  onchange={() => { newNodeRole = defaultRoleForType(newNodeType); }}>
                  {#each promptNodeTypes as t}<option value={t}>{t}</option>{/each}
                </select>
              </label>
              <label class="visual-field">
                <span class="visual-field-label">role</span>
                <select class="compact-input" bind:value={newNodeRole}>
                  {#each promptRoles as r}<option value={r}>{r}</option>{/each}
                </select>
              </label>
              {#if newNodeType === "file"}
                <label class="visual-field">
                  <span class="visual-field-label">path</span>
                  <select class="compact-input" bind:value={newNodePath}>
                    {#each files.map((f) => f.path) as p}<option value={p}>{p}</option>{/each}
                  </select>
                </label>
              {/if}
              <label class="visual-field visual-field-check">
                <span class="visual-field-label">required</span>
                <input type="checkbox" bind:checked={newNodeRequired} />
              </label>
              {#if newNodeError}
                <p class="mini-error">{newNodeError}</p>
              {/if}
              <div class="visual-order-actions">
                <button type="button" class="primary-button" onclick={submitAddNode}>{$t("editor.add")}</button>
                <button type="button" onclick={() => { addingNode = false; newNodeError = ""; }}>{$t("common.cancel")}</button>
              </div>
            </div>
          {/if}

          {#key selectedVisualNodeId}
          {#if selectedPromptNode}
            {@const node = selectedPromptNode}
            {@const idx = selectedPromptNodeIndex}
            <div class="visual-node-edit">
              <label class="visual-field">
                <span class="visual-field-label">id</span>
                <input
                  class="compact-input"
                  type="text"
                  value={node?.id}
                  onchange={(e) => {
                    const err = renameNode(idx, e.currentTarget.value);
                    if (err) { e.currentTarget.value = node?.id ?? ""; e.currentTarget.setCustomValidity(err); e.currentTarget.reportValidity(); }
                    else { e.currentTarget.setCustomValidity(""); }
                  }}
                />
              </label>
              <label class="visual-field">
                <span class="visual-field-label">type</span>
                <select class="compact-input" value={node?.type}
                  onchange={(e) => changeNodeType(idx, node ?? {}, e.currentTarget.value)}>
                  {#each promptNodeTypes as pt}<option value={pt}>{pt}</option>{/each}
                </select>
              </label>
              <label class="visual-field">
                <span class="visual-field-label">role</span>
                <select class="compact-input" value={node?.role}
                  onchange={(e) => updateNodeField(idx, "role", e.currentTarget.value)}>
                  {#each promptRoles as r}<option value={r}>{r}</option>{/each}
                </select>
              </label>
              <label class="visual-field">
                <span class="visual-field-label">order</span>
                <input
                  class="compact-input"
                  type="number"
                  value={node?.order ?? ""}
                  onchange={(e) => updateNodeOrder(idx, e.currentTarget.value)}
                />
              </label>
              <label class="visual-field visual-field-check">
                <span class="visual-field-label">required</span>
                <input type="checkbox" checked={node?.required}
                  onchange={(e) => updateNodeField(idx, "required", e.currentTarget.checked)} />
              </label>
              {#if node?.type === "file"}
                <label class="visual-field">
                  <span class="visual-field-label">path</span>
                  <select class="compact-input" value={node?.path || ""}
                    onchange={(e) => updateNodeField(idx, "path", e.currentTarget.value)}>
                    {#each fileNodePathOptions(node || {}) as p}<option value={p}>{p}</option>{/each}
                  </select>
                </label>
              {/if}
              <label class="visual-field">
                <span class="visual-field-label">condition</span>
                <select class="compact-input" value={conditionMode(node || {})}
                  onchange={(e) => updateCondition(idx, node || {}, e.currentTarget.value)}>
                  <option value="none">{$t("editor.condNone")}</option>
                  <option value="image_enabled">{$t("editor.condImageOn")}</option>
                  <option value="image_disabled">{$t("editor.condImageOff")}</option>
                </select>
              </label>
              {#if node?.type === "rag" || node?.type === "session_log"}
                <label class="visual-field visual-field-check">
                  <span class="visual-field-label">budget</span>
                  <input
                    type="checkbox"
                    checked={budgetEnabled(node || {})}
                    onchange={(e) => updateBudgetEnabled(idx, e.currentTarget.checked)}
                  />
                </label>
                {#if budgetEnabled(node || {})}
                  <label class="visual-field">
                    <span class="visual-field-label">token budget</span>
                    <input class="compact-input" type="number" min="0" value={node?.token_budget ?? ""}
                      oninput={(e) => updateOptionalNumberField(idx, "token_budget", e.currentTarget.value)} />
                  </label>
                {:else}
                  <p class="hint-copy">Budget disabled for this node.</p>
                {/if}
              {/if}
              {#if node?.type === "rag"}
                <fieldset class="visual-field rag-source-options">
                  <legend class="visual-field-label">{$t("editor.ragSources")}</legend>
                  {#each RAG_SOURCE_OPTIONS as source}
                    <label class="inline-check compact-check">
                      <input
                        type="checkbox"
                        checked={ragSourceChecked(node || {}, source)}
                        onchange={(e) => updateRagSource(idx, source, e.currentTarget.checked)}
                      />
                      <span>{source}</span>
                    </label>
                  {/each}
                </fieldset>
                <label class="visual-field">
                  <span class="visual-field-label">limit</span>
                  <input class="compact-input" type="number" min="0" value={node?.limit ?? ""}
                    title={$t("editor.ragLimitHelp")}
                    oninput={(e) => updateOptionalNumberField(idx, "limit", e.currentTarget.value)} />
                </label>
                <fieldset class="visual-field type-budgets">
                  <legend class="visual-field-label">{$t("editor.ragTypeLimits")}</legend>
                  {#each RAG_TYPE_LIMIT_KEYS as key}
                    <label class="visual-field">
                      <span class="visual-field-label">{key}</span>
                      <input
                        class="compact-input"
                        type="number"
                        min="0"
                        step="1"
                        value={ragTypeLimitValue(node || {}, key)}
                        placeholder={key}
                        title={$t("editor.ragTypeLimitHelp")}
                        oninput={(e) => updateRagTypeLimit(idx, key, e.currentTarget.value)}
                      />
                    </label>
                  {/each}
                </fieldset>
                {#if budgetEnabled(node || {})}
                  <label class="visual-field">
                    <span class="visual-field-label">keyword token budget</span>
                    <input class="compact-input" type="number" min="0" value={node?.keyword_token_budget ?? ""}
                      title={$t("editor.ragKeywordBudgetHelp")}
                      oninput={(e) => updateOptionalNumberField(idx, "keyword_token_budget", e.currentTarget.value)} />
                  </label>
                  <fieldset class="visual-field type-budgets">
                    <legend class="visual-field-label">{$t("editor.ragTypeBudgets")}</legend>
                    {#each RAG_TYPE_BUDGET_KEYS as key}
                      <label class="visual-field">
                        <span class="visual-field-label">{key}</span>
                        <input
                          class="compact-input"
                          type="number"
                          min="0"
                          value={ragTypeBudgetValue(node || {}, key)}
                          placeholder={key}
                          title={$t("editor.ragTypeBudgetHelp")}
                          oninput={(e) => updateRagTypeBudget(idx, key, e.currentTarget.value)}
                        />
                      </label>
                    {/each}
                  </fieldset>
                  <p class="hint-copy">{$t("editor.ragBudgetHint")}</p>
                {/if}
              {/if}
            </div>

            <div class="visual-order-actions">
              <button
                type="button"
                disabled={idx <= 0}
                onclick={() => moveNode(idx, "up")}
              >
                <ArrowUp size={15} aria-hidden="true" /> {$t("editor.moveUp")}
              </button>
              <button
                type="button"
                disabled={idx >= promptNodeList.length - 1}
                onclick={() => moveNode(idx, "down")}
              >
                <ArrowDown size={15} aria-hidden="true" /> {$t("editor.moveDown")}
              </button>
            </div>
          {:else if !addingNode}
            <p class="notice">{$t("editor.nodeSelectHint")}</p>
          {/if}
          {/key}
        </aside>
      </div>
    {/if}
  {/if}
{:else}
  <p class="notice">{$t("editor.noGraph")}</p>
{/if}
</div>

{#if manifestModalOpen}
  <div class="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="manifest-modal-heading">
    <button class="modal-scrim" type="button" aria-label={$t("common.close")} onclick={() => { manifestModalOpen = false; }}></button>
    <div class="picker-modal create-source-modal">
      <div class="panel-header compact">
        <h3 id="manifest-modal-heading">manifest: {manifestModalStartId}</h3>
        <button class="icon-button" type="button" title={$t("common.close")} onclick={() => { manifestModalOpen = false; }}>
          <X size={18} aria-hidden="true" />
        </button>
      </div>
      <label class="visual-field">
        <span class="visual-field-label">{$t("editor.startName")}</span>
        <input class="compact-input" type="text" bind:value={manifestName} placeholder={manifestModalStartId} />
      </label>
      <label class="visual-field">
        <span class="visual-field-label">description</span>
        <input class="compact-input" type="text" bind:value={manifestDescription} />
      </label>
      <label class="visual-field">
        <span class="visual-field-label">{$t("editor.startLoreInclude")}</span>
        <input class="compact-input" type="text" bind:value={manifestLoreInclude} placeholder="id1, id2" />
      </label>
      <label class="visual-field">
        <span class="visual-field-label">{$t("editor.startLoreExclude")}</span>
        <input class="compact-input" type="text" bind:value={manifestLoreExclude} placeholder="id1, id2" />
      </label>
      <label class="visual-field">
        <span class="visual-field-label">{$t("editor.startInitialState")}</span>
        <input class="compact-input" type="text" bind:value={manifestInitialState} placeholder="initial_state.json" />
      </label>
      {#if manifestMessage}<p class="mini-ok">{manifestMessage}</p>{/if}
      {#if manifestError}<p class="mini-error">{manifestError}</p>{/if}
      <div class="modal-row-actions">
        <button type="button" disabled={savingManifest || !manifestName.trim()} onclick={() => void saveManifest()}>
          <Save size={15} aria-hidden="true" /> {savingManifest ? $t("editor.saving") : $t("editor.save")}
        </button>
        <button type="button" onclick={() => { manifestModalOpen = false; }}>{$t("common.cancel")}</button>
      </div>
    </div>
  </div>
{/if}

{#if duplicateGraphModal}
  <div class="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="dup-graph-modal-heading">
    <button class="modal-scrim" type="button" aria-label={$t("common.close")} onclick={() => { duplicateGraphModal = false; }}></button>
    <div class="picker-modal create-source-modal">
      <div class="panel-header compact">
        <h3 id="dup-graph-modal-heading"><Copy size={16} aria-hidden="true" /> {$t("editor.duplicateGraph")}</h3>
        <button class="icon-button" type="button" title={$t("common.close")} onclick={() => { duplicateGraphModal = false; }}>
          <X size={18} aria-hidden="true" />
        </button>
      </div>
      <p style="font-size:0.85rem;">{$t("editor.duplicateGraphDesc")}</p>
      <label>
        <span>{$t("editor.duplicateGraphTarget")}</span>
        <select bind:value={duplicateGraphTargetId}>
          {#each starts as start}
            <option value={start.id}>{start.name || start.id}</option>
          {/each}
        </select>
      </label>
      {#if duplicateGraphMessage}<p class="mini-ok">{duplicateGraphMessage}</p>{/if}
      {#if duplicateGraphError}<p class="mini-error">{duplicateGraphError}</p>{/if}
      <div class="modal-row-actions">
        <button type="button" disabled={duplicatingGraph || !duplicateGraphTargetId} onclick={() => void duplicateGraphToStart()}>
          <Copy size={15} aria-hidden="true" /> {duplicatingGraph ? $t("editor.saving") : $t("editor.copy")}
        </button>
        <button type="button" onclick={() => { duplicateGraphModal = false; }}>{$t("common.cancel")}</button>
      </div>
    </div>
  </div>
{/if}

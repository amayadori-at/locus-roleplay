<script>
  import { ArrowLeft, ArrowDown, ArrowUp, Copy, FilePenLine, FilePlus2, GitBranch, ListTree, Minimize2, Plus, RotateCcw, Save, Trash2, X } from "lucide-svelte";
  import { Background, BackgroundVariant, Controls, SvelteFlow } from "@xyflow/svelte";
  import "@xyflow/svelte/dist/style.css";
  import { onMount } from "svelte";
  import {
    createScenarioSourceFile,
    deleteScenarioSourceFile,
    getScenarioPromptPreview,
    getScenarioPromptGraph,
    getScenarioRagStatus,
    getScenarioRagVectorStatus,
    getScenarioSettings,
    getScenarioSourceFile,
    getStartManifest,
    getStartPromptGraph,
    listPersonas,
    listProfiles,
    listScenarioSessions,
    listScenarioSourceFiles,
    listScenarioStarts,
    rebuildScenarioRagIndex,
    rebuildScenarioVectorIndex,
    updateScenarioSettings,
    updateScenarioSourceFile,
    updateScenarioPromptGraph,
    updateStartManifest,
    updateStartPromptGraph
  } from "../lib/api.js";
  import { t, translateNow } from "../lib/i18n.js";
  import PromptPreviewPanel from "../lib/PromptPreviewPanel.svelte";
  import SourceEditorPanel from "../lib/SourceEditorPanel.svelte";

  /** @type {{ scenarioId?: string, mode?: string, query?: Record<string, string> }} */
  export let route;
  export let onNavigate = {
    openHome: () => {}
  };

  /** @type {Array<{ path: string, size?: number }>} */
  let files = [];
  let selectedPath = "";
  let content = "";
  let sourceContent = "";
  let sourceDirty = false;
  let savingSource = false;
  let deletingSource = false;
  let sourceMessage = "";
  let creatingSource = false;
  let newSourceKind = "characters";
  let newSourceId = "";
  let newSourceName = "";
  let newSourceError = "";
  let loading = true;
  let loadingFile = false;
  let loadingPromptGraph = false;
  let loadingPreviewChoices = false;
  let loadingPromptPreview = false;
  let savingPromptGraph = false;
  let error = "";
  let promptGraphError = "";
  let promptGraphMessage = "";
  let promptPreviewError = "";
  let activeTab = "markdown";
  /** @type {"table" | "visual"} */
  let promptView = "table";
  /** @type {Record<string, any> | null} */
  let promptGraph = null;
  let promptGraphSource = "";
  let promptGraphDirty = false;
  /** @type {Record<string, any> | null} */
  let promptPreview = null;
  /** @type {Array<Record<string, any>>} */
  let sessions = [];
  /** @type {Array<Record<string, any>>} */
  let personas = [];
  /** @type {Array<Record<string, any>>} */
  let profiles = [];
  let previewSessionId = "";
  let previewPersonaId = "";
  let previewProfileId = "";
  let previewUserMessage = translateNow("editor.previewUserInput");
  let selectedVisualNodeId = "";
  /** @type {Array<string>} */
  let promptGraphWarnings = [];
  const promptRoles = ["system", "user", "assistant", "messages"];
  const promptNodeTypes = ["file", "selected_persona", "state", "rag", "session_log", "user_note", "scene_note", "current_user_message", "condition", "output"];

  let createFileModalOpen = false;
  let sourceEditorExpanded = false;
  let isMobile = false;

  let addingNode = false;
  let newNodeId = "";
  let newNodeType = "file";
  let newNodeRole = "system";
  let newNodePath = "";
  let newNodeRequired = false;
  let newNodeError = "";

  /** @type {Array<Record<string, any>>} */
  let starts = [];
  let startsLoading = false;
  let startsError = "";
  let addingStart = false;
  let newStartId = "";
  let newStartName = "";
  let newStartBody = "";
  let newStartError = "";
  let creatingStart = false;
  let deletingStartId = "";

  /** @type {{ prompt_graph_mode: string }} */
  let scenarioSettings = { prompt_graph_mode: "common" };
  let savingSettings = false;
  let settingsMessage = "";
  let settingsError = "";
  /** Currently selected start tab in per_start mode */
  let selectedStartTabId = "";
  /** Whether the current promptGraph belongs to a specific start (per_start mode) */
  let activeStartId = "";
  /** true when the loaded graph is the start's own (not inherited) */
  let currentGraphOwnFlag = true;
  /** PG-2: duplicate-to-start modal */
  let duplicateGraphModal = false;
  let duplicateGraphTargetId = "";
  let duplicatingGraph = false;
  let duplicateGraphMessage = "";
  let duplicateGraphError = "";

  let manifestModalOpen = false;
  let manifestModalStartId = "";
  let manifestName = "";
  let manifestDescription = "";
  let manifestLoreInclude = "";
  let manifestLoreExclude = "";
  let manifestInitialState = "";
  let savingManifest = false;
  let manifestMessage = "";
  let manifestError = "";

  /** @type {Record<string, any> | null} */
  let ragStatus = null;
  let ragStatusLoading = false;
  let ragStatusError = "";
  /** @type {Record<string, any> | null} */
  let vectorStatus = null;
  let vectorStatusLoading = false;
  let vectorStatusError = "";
  let rebuildingRagIndex = false;
  let rebuildingVectorIndex = false;
  let ragRebuildMessage = "";
  let vectorRebuildMessage = "";

  onMount(async () => {
    const mq = window.matchMedia("(max-width: 860px)");
    isMobile = mq.matches;
    mq.addEventListener("change", (e) => { isMobile = e.matches; });
    await loadFiles();
  });

  async function loadFiles() {
    if (!route.scenarioId) {
      error = translateNow("session.noScenario");
      loading = false;
      return;
    }
    loading = true;
    error = "";
    try {
      const payload = await listScenarioSourceFiles(route.scenarioId);
      files = payload.files || [];
      const requestedPath = route.query?.source || "";
      selectedPath = files.some((file) => file.path === requestedPath) ? requestedPath : files[0]?.path || "";
      if (selectedPath) {
        await loadFile(selectedPath);
      }
      await Promise.all([loadPromptGraph(), loadPreviewChoices(), loadScenarioSettings()]);
    } catch (caught) {
      error = caught instanceof Error ? caught.message : translateNow("editor.loadFilesError");
    } finally {
      loading = false;
    }
  }

  /** @param {string} path */
  async function loadFile(path) {
    if (!route.scenarioId) {
      return;
    }
    selectedPath = path;
    loadingFile = true;
    error = "";
    try {
      const payload = await getScenarioSourceFile(route.scenarioId, path);
      content = payload.content || "";
      sourceContent = content;
      sourceDirty = false;
      sourceMessage = "";
    } catch (caught) {
      error = caught instanceof Error ? caught.message : translateNow("editor.loadFileError");
    } finally {
      loadingFile = false;
    }
  }

  async function saveSourceFile() {
    if (!route.scenarioId || !selectedPath || savingSource || !sourceDirty) {
      return;
    }
    savingSource = true;
    error = "";
    sourceMessage = "";
    try {
      const payload = await updateScenarioSourceFile(route.scenarioId, selectedPath, sourceContent);
      content = payload.content || sourceContent;
      sourceContent = content;
      sourceDirty = false;
      sourceMessage = translateNow("editor.saved");
      files = files.map((file) => (file.path === selectedPath ? { ...file, size: content.length } : file));
    } catch (caught) {
      error = caught instanceof Error ? caught.message : translateNow("editor.saveFileError");
    } finally {
      savingSource = false;
    }
  }

  function canDeleteSelectedSource() {
    if (!selectedPath) return false;
    const [directory, filename, extra] = selectedPath.split("/");
    return !extra && ["gm", "characters", "lore", "startings"].includes(directory) && /^[A-Za-z0-9_-]+\.md$/.test(filename || "");
  }

  async function deleteSourceFile() {
    if (!route.scenarioId || !selectedPath || deletingSource || sourceDirty || !canDeleteSelectedSource()) {
      return;
    }
    const pathToDelete = selectedPath;
    const isStart = pathToDelete.startsWith("startings/") && pathToDelete.split("/").length === 2;
    const confirmKey = isStart ? "editor.deleteStartConfirm" : "editor.deleteConfirm";
    if (!window.confirm(translateNow(confirmKey, { path: pathToDelete }))) {
      return;
    }
    deletingSource = true;
    error = "";
    sourceMessage = "";
    try {
      const deletedIndex = files.findIndex((file) => file.path === pathToDelete);
      await deleteScenarioSourceFile(route.scenarioId, pathToDelete);
      const nextFilesPayload = await listScenarioSourceFiles(route.scenarioId);
      const nextFiles = nextFilesPayload.files || [];
      files = nextFiles;
      const fallbackPath = nextFiles[deletedIndex]?.path || nextFiles[Math.max(0, deletedIndex - 1)]?.path || nextFiles[0]?.path || "";
      if (fallbackPath) {
        await loadFile(fallbackPath);
        sourceMessage = translateNow("editor.deleteSuccess", { path: pathToDelete });
      } else {
        selectedPath = "";
        content = "";
        sourceContent = "";
        sourceDirty = false;
        sourceMessage = translateNow("editor.deleteSuccess", { path: pathToDelete });
      }
      await loadPromptGraph();
    } catch (caught) {
      error = caught instanceof Error ? caught.message : translateNow("editor.deleteError");
    } finally {
      deletingSource = false;
    }
  }

  function resetSourceEdits() {
    sourceContent = content;
    sourceDirty = false;
    sourceMessage = "";
  }

  /** @param {Event} event */
  function updateSourceDraft(event) {
    const target = event.currentTarget;
    if (!(target instanceof HTMLTextAreaElement)) {
      return;
    }
    sourceContent = target.value;
    sourceDirty = sourceContent !== content;
    sourceMessage = "";
  }

  function newSourcePath() {
    const id = newSourceId.trim();
    if (!id) return "";
    return `${newSourceKind}/${id}.md`;
  }

  function newSourceTemplate() {
    const id = newSourceId.trim();
    const name = newSourceName.trim() || id;
    if (newSourceKind === "characters") {
      return `---\ntype: character\nid: ${id}\nname: ${name}\n---\n\n# ${name}\n\n`;
    }
    if (newSourceKind === "lore") {
      return `---\ntype: lore\nid: ${id}\nname: ${name}\nrag: true\n---\n\n# ${name}\n\n`;
    }
    if (newSourceKind === "startings") {
      return `---\ntype: starting\nid: ${id}\nname: ${name}\n---\n\n${translateNow("editor.startingTemplate", { name })}`;
    }
    return `---\ntype: gm_prompt\nid: ${id}\n---\n\n# ${name}\n\n`;
  }

  function validateNewSourceInput() {
    const id = newSourceId.trim();
    if (!/^[A-Za-z0-9_-]+$/.test(id)) {
      return translateNow("editor.invalidId");
    }
    if (files.some((file) => file.path === newSourcePath())) {
      return translateNow("editor.duplicatePath");
    }
    return "";
  }

  async function createSourceFile() {
    if (!route.scenarioId || creatingSource) {
      return;
    }
    newSourceError = validateNewSourceInput();
    if (newSourceError) {
      return;
    }
    creatingSource = true;
    error = "";
    sourceMessage = "";
    try {
      const path = newSourcePath();
      const payload = await createScenarioSourceFile(route.scenarioId, path, newSourceTemplate());
      const filesPayload = await listScenarioSourceFiles(route.scenarioId);
      files = filesPayload.files || [];
      newSourceId = "";
      newSourceName = "";
      newSourceError = "";
      createFileModalOpen = false;
      await loadFile(payload.path || path);
      activeTab = "markdown";
      sourceMessage = translateNow("editor.fileCreated");
    } catch (caught) {
      newSourceError = caught instanceof Error ? caught.message : translateNow("editor.createFileError");
    } finally {
      creatingSource = false;
    }
  }

  async function loadPromptGraph() {
    if (!route.scenarioId) {
      return;
    }
    loadingPromptGraph = true;
    promptGraphError = "";
    try {
      const payload = await getScenarioPromptGraph(route.scenarioId);
      promptGraph = payload.graph || null;
      promptGraphSource = payload.source || "";
      promptGraphWarnings = payload.warnings || [];
      promptGraphDirty = false;
      promptGraphMessage = "";
      selectedVisualNodeId = promptGraph?.nodes?.[0]?.id || "";
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

  async function loadPreviewChoices() {
    if (!route.scenarioId) {
      return;
    }
    loadingPreviewChoices = true;
    promptPreviewError = "";
    try {
      const [sessionPayload, personaPayload, profilePayload] = await Promise.all([
        listScenarioSessions(route.scenarioId),
        listPersonas(),
        listProfiles()
      ]);
      sessions = sessionPayload.sessions || [];
      personas = personaPayload.personas || [];
      profiles = profilePayload.profiles || [];
      previewSessionId = sessions[0]?.session_id || "";
      previewPersonaId = personas[0]?.id || "";
      previewProfileId = roleplayProfiles()[0]?.id || profiles[0]?.id || "";
    } catch (caught) {
      promptPreviewError = caught instanceof Error ? caught.message : translateNow("editor.loadPreviewError");
    } finally {
      loadingPreviewChoices = false;
    }
  }

  /** @returns {Array<Record<string, any>>} */
  function promptNodes() {
    return promptGraph?.nodes || [];
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
    const nodes = [...(promptGraph.nodes || [])];
    nodes[index] = { ...nodes[index], [field]: value };
    promptGraph = { ...promptGraph, nodes };
    markPromptGraphDirty();
  }

  /**
   * @param {number} index
   * @param {Record<string, any>} nextNode
   */
  function updateNode(index, nextNode) {
    if (!promptGraph) return;
    const nodes = [...(promptGraph.nodes || [])];
    nodes[index] = nextNode;
    promptGraph = { ...promptGraph, nodes };
    markPromptGraphDirty();
  }

  /**
   * @param {number} index
   * @param {"up" | "down"} direction
   */
  function moveNode(index, direction) {
    if (!promptGraph) return;
    const nodes = [...(promptGraph.nodes || [])];
    const nextIndex = direction === "up" ? index - 1 : index + 1;
    if (nextIndex < 0 || nextIndex >= nodes.length) return;
    [nodes[index], nodes[nextIndex]] = [nodes[nextIndex], nodes[index]];
    const reordered = nodes.map((node, nodeIndex) => ({ ...node, order: (nodeIndex + 1) * 10 }));
    promptGraph = { ...promptGraph, nodes: reordered };
    markPromptGraphDirty();
  }

  /**
   * @param {string} value
   * @returns {number | undefined}
   */
  function optionalNumber(value) {
    const trimmed = value.trim();
    if (!trimmed) return undefined;
    const parsed = Number(trimmed);
    return Number.isFinite(parsed) ? parsed : undefined;
  }

  async function savePromptGraph() {
    if (!route.scenarioId || !promptGraph || savingPromptGraph) return;
    savingPromptGraph = true;
    promptGraphError = "";
    promptGraphMessage = "";
    try {
      const payload = await updateScenarioPromptGraph(route.scenarioId, promptGraph);
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
    if (!route.scenarioId || !previewUserMessage.trim() || loadingPromptPreview) {
      return;
    }
    loadingPromptPreview = true;
    promptPreviewError = "";
    try {
      promptPreview = await getScenarioPromptPreview(route.scenarioId, {
        session_id: previewSessionId,
        persona_id: previewSessionId ? "" : previewPersonaId,
        profile_id: previewSessionId ? "" : previewProfileId,
        user_message: previewUserMessage
      });
    } catch (caught) {
      promptPreviewError = caught instanceof Error ? caught.message : translateNow("editor.previewError");
      promptPreview = null;
    } finally {
      loadingPromptPreview = false;
    }
  }

  /** @param {Record<string, any>} node */
  function nodeSource(node) {
    if (node.path) return node.path;
    if (Array.isArray(node.source)) return node.source.join(", ");
    return node.source || node.type || "runtime";
  }

  /** @param {Record<string, any>} node */
  function nodeCondition(node) {
    return node.condition ? JSON.stringify(node.condition) : "";
  }

  function visualNodes() {
    const nodes = promptNodes().map((node, index) => ({
      id: node.id,
      type: index === 0 ? "input" : "default",
      data: {
        label: `${node.order} ${node.id}\n${node.type} / ${node.role}`
      },
      position: { x: index * 220, y: node.condition ? 110 : 40 },
      class: `prompt-flow-node prompt-flow-${node.type}${node.required ? " required" : ""}`
    }));
    if (nodes.length) {
      nodes.push({
        id: "final_prompt",
        type: "output",
        data: { label: "⬛ final prompt" },
        position: { x: nodes.length * 220, y: 40 },
        class: "prompt-flow-node prompt-flow-final"
      });
    }
    return nodes;
  }

  function visualEdges() {
    const ids = promptNodes().map((node) => node.id);
    if (ids.length) {
      ids.push("final_prompt");
    }
    return ids.slice(0, -1).map((source, index) => ({
      id: `${source}-${ids[index + 1]}`,
      source,
      target: ids[index + 1],
      animated: source === selectedVisualNodeId
    }));
  }

  function selectedVisualNode() {
    return promptNodes().find((node) => node.id === selectedVisualNodeId) || null;
  }

  /** @param {string} nodeId */
  function selectVisualNode(nodeId) {
    selectedVisualNodeId = nodeId === "final_prompt" ? "" : nodeId;
  }

  function selectedVisualNodeIndex() {
    const node = selectedVisualNode();
    if (!node) return -1;
    return promptNodes().findIndex((item) => item.id === node.id);
  }

  /** @param {number} index */
  function deleteNode(index) {
    if (!promptGraph) return;
    const nodes = [...(promptGraph.nodes || [])];
    nodes.splice(index, 1);
    promptGraph = { ...promptGraph, nodes };
    selectedVisualNodeId = "";
    markPromptGraphDirty();
  }

  /** @param {number} index */
  function duplicateNode(index) {
    if (!promptGraph) return;
    const nodes = [...(promptGraph.nodes || [])];
    const source = nodes[index];
    const maxOrder = nodes.reduce((max, n) => Math.max(max, n.order ?? 0), 0);
    let uniqueId = `${source.id}_copy`;
    let suffix = 2;
    while (nodes.some((n) => n.id === uniqueId)) {
      uniqueId = `${source.id}_copy${suffix}`;
      suffix++;
    }
    const duplicated = { ...source, id: uniqueId, order: maxOrder + 10 };
    promptGraph = { ...promptGraph, nodes: [...nodes, duplicated] };
    selectedVisualNodeId = uniqueId;
    markPromptGraphDirty();
  }

  /** @param {string} type */
  function defaultRoleForType(type) {
    if (type === "current_user_message") return "user";
    if (type === "session_log") return "messages";
    return "system";
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
    const updated = [...nodes];
    updated[index] = { ...updated[index], id };
    promptGraph = { ...promptGraph, nodes: updated };
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
    /** @type {Record<string, any>} */
    const next = { ...node, type: newType };
    const shouldHavePath = newType === "file";
    if (shouldHavePath && !next.path) {
      next.path = files[0]?.path || "scenario.md";
    } else if (!shouldHavePath) {
      delete next.path;
    }
    const defaultRole = defaultRoleForType(newType);
    if (node.role !== defaultRole && (newType === "current_user_message" || newType === "session_log")) {
      next.role = defaultRole;
    }
    updateNode(index, next);
  }

  function submitAddNode() {
    newNodeError = "";
    const id = newNodeId.trim();
    if (!id) { newNodeError = translateNow("editor.idRequired"); return; }
    if (!/^[a-z0-9_]+$/.test(id)) { newNodeError = translateNow("editor.idInvalid"); return; }
    if (promptNodes().some((n) => n.id === id)) { newNodeError = translateNow("editor.idExists", { id }); return; }
    const maxOrder = promptNodes().reduce((max, n) => Math.max(max, n.order ?? 0), 0);
    /** @type {Record<string, any>} */
    const newNode = {
      id,
      type: newNodeType,
      role: newNodeRole,
      order: maxOrder + 10,
      required: newNodeRequired,
    };
    if (newNodeType === "file") {
      newNode.path = newNodePath || files[0]?.path || "scenario.md";
    }
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

  async function loadStarts() {
    if (!route.scenarioId) return;
    startsLoading = true;
    startsError = "";
    try {
      const payload = await listScenarioStarts(route.scenarioId);
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
    if (!route.scenarioId) return;
    try {
      const payload = await getScenarioSettings(route.scenarioId);
      scenarioSettings = payload.settings || { prompt_graph_mode: "common" };
    } catch {
      // non-fatal: keep defaults
    }
  }

  async function saveScenarioSettings(newSettings = scenarioSettings) {
    if (!route.scenarioId || savingSettings) return;
    savingSettings = true;
    settingsMessage = "";
    settingsError = "";
    try {
      const payload = await updateScenarioSettings(route.scenarioId, newSettings);
      scenarioSettings = payload.settings || newSettings;
      settingsMessage = translateNow("editor.saved");
    } catch (caught) {
      settingsError = caught instanceof Error ? caught.message : translateNow("editor.saveGraphError");
    } finally {
      savingSettings = false;
    }
  }

  /** @param {string} startId Load a start's prompt graph into the editor. */
  async function loadStartPromptGraph(startId) {
    if (!route.scenarioId) return;
    loadingPromptGraph = true;
    promptGraphError = "";
    try {
      const payload = await getStartPromptGraph(route.scenarioId, startId);
      promptGraph = payload.graph || null;
      promptGraphSource = payload.source || "start";
      promptGraphWarnings = payload.warnings || [];
      promptGraphDirty = false;
      promptGraphMessage = "";
      currentGraphOwnFlag = payload.own_graph ?? true;
      activeStartId = startId;
      selectedVisualNodeId = promptGraph?.nodes?.[0]?.id || "";
    } catch (caught) {
      promptGraphError = caught instanceof Error ? caught.message : translateNow("editor.loadGraphError");
      promptGraph = null;
    } finally {
      loadingPromptGraph = false;
    }
  }

  /** Save current graph. Routes to start-specific or scenario-level depending on mode. */
  async function savePromptGraphRouted() {
    if (!route.scenarioId || !promptGraph || savingPromptGraph) return;
    if (scenarioSettings.prompt_graph_mode === "per_start" && activeStartId) {
      savingPromptGraph = true;
      promptGraphError = "";
      promptGraphMessage = "";
      try {
        const payload = await updateStartPromptGraph(route.scenarioId, activeStartId, promptGraph);
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
    if (!route.scenarioId || !promptGraph || !duplicateGraphTargetId || duplicatingGraph) return;
    duplicatingGraph = true;
    duplicateGraphMessage = "";
    duplicateGraphError = "";
    try {
      const graphToCopy = { ...promptGraph, id: duplicateGraphTargetId };
      await updateStartPromptGraph(route.scenarioId, duplicateGraphTargetId, graphToCopy);
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
    selectedStartTabId = startId;
    await loadStartPromptGraph(startId);
  }

  /** @param {string} startId */
  async function openManifestModal(startId) {
    if (!route.scenarioId) return;
    manifestModalStartId = startId;
    manifestMessage = "";
    manifestError = "";
    manifestName = "";
    manifestDescription = "";
    manifestLoreInclude = "";
    manifestLoreExclude = "";
    manifestInitialState = "";
    try {
      const payload = await getStartManifest(route.scenarioId, startId);
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
    if (!route.scenarioId || !manifestModalStartId || savingManifest) return;
    savingManifest = true;
    manifestMessage = "";
    manifestError = "";
    const parseIds = (/** @type {string} */ raw) =>
      raw.split(",").map((s) => s.trim()).filter(Boolean);
    try {
      await updateStartManifest(route.scenarioId, manifestModalStartId, {
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

  async function loadRagStatus() {
    if (!route.scenarioId) return;
    ragStatusLoading = true;
    ragStatusError = "";
    vectorStatusLoading = true;
    vectorStatusError = "";
    ragRebuildMessage = "";
    vectorRebuildMessage = "";
    try {
      ragStatus = await getScenarioRagStatus(route.scenarioId);
    } catch (caught) {
      ragStatusError = caught instanceof Error ? caught.message : translateNow("editor.ragStatusError");
    } finally {
      ragStatusLoading = false;
    }
    try {
      vectorStatus = await getScenarioRagVectorStatus(route.scenarioId);
    } catch (caught) {
      vectorStatusError = caught instanceof Error ? caught.message : translateNow("editor.vectorStatusError");
    } finally {
      vectorStatusLoading = false;
    }
  }

  async function doRebuildRagIndex() {
    if (!route.scenarioId || rebuildingRagIndex) return;
    rebuildingRagIndex = true;
    ragRebuildMessage = "";
    try {
      const result = await rebuildScenarioRagIndex(route.scenarioId);
      ragRebuildMessage = translateNow("editor.rebuildDone", { count: result.index?.document_count ?? 0 });
      ragStatus = await getScenarioRagStatus(route.scenarioId);
    } catch (caught) {
      ragRebuildMessage = caught instanceof Error ? caught.message : translateNow("editor.rebuildError");
    } finally {
      rebuildingRagIndex = false;
    }
  }

  async function doRebuildVectorIndex() {
    if (!route.scenarioId || rebuildingVectorIndex) return;
    rebuildingVectorIndex = true;
    vectorRebuildMessage = "";
    try {
      const result = await rebuildScenarioVectorIndex(route.scenarioId);
      vectorRebuildMessage = translateNow("editor.vectorRebuildDone", { count: result.index?.document_count ?? 0, model: result.index?.model ?? "" });
      vectorStatus = await getScenarioRagVectorStatus(route.scenarioId);
    } catch (caught) {
      vectorRebuildMessage = caught instanceof Error ? caught.message : translateNow("editor.vectorRebuildError");
    } finally {
      rebuildingVectorIndex = false;
    }
  }
</script>

<div class="toolbar">
  <div>
    <p class="eyebrow">Scenario</p>
    <h2 id="workspace-heading">{route.scenarioId || "Scenario Page"}</h2>
  </div>
  <button class="icon-button" type="button" title="Front Page" onclick={onNavigate.openHome}>
    <ArrowLeft size={18} aria-hidden="true" />
  </button>
</div>

{#if error}
  <p class="notice error-notice">{error}</p>
{/if}

{#if loading}
  <p class="notice">{$t("editor.loadingFiles")}</p>
{:else}
  <div class="editor-layout">
    <aside class="panel source-tree" aria-labelledby="source-tree-heading">
      <div class="source-tree-header">
        <h3 id="source-tree-heading"><ListTree size={18} aria-hidden="true" /> Vault Tree</h3>
        <button
          class="icon-button compact-icon"
          type="button"
          title={$t("editor.newFile")}
          onclick={() => { createFileModalOpen = true; newSourceError = ""; }}
        >
          <FilePlus2 size={16} aria-hidden="true" />
        </button>
      </div>
      {#if files.length}
        <ul class="select-list">
          {#each files as file}
            <li>
              <button
                class:selected={file.path === selectedPath}
                type="button"
                disabled={sourceDirty}
                title={sourceDirty ? $t("editor.unsavedWarning") : file.path}
                onclick={() => loadFile(file.path)}
              >
                <strong>{file.path}</strong>
                <span>{file.size || 0} bytes</span>
              </button>
            </li>
          {/each}
        </ul>
      {:else}
        <p>{$t("editor.noFiles")}</p>
      {/if}
    </aside>

    <section class="panel editor-panel" aria-labelledby="editor-heading">
      <div class="panel-header compact">
        <h3 id="editor-heading"><FilePenLine size={18} aria-hidden="true" /> {selectedPath || "No file"}</h3>
        <div class="segmented-control">
          <button class:selected={activeTab === "markdown"} type="button" onclick={() => (activeTab = "markdown")}>
            Markdown
          </button>
          <button class:selected={activeTab === "prompt"} type="button" onclick={() => { activeTab = "prompt"; if (!starts.length) void loadStarts(); }}>
            Prompt
          </button>
          <button class:selected={activeTab === "rag"} type="button" onclick={() => { activeTab = "rag"; void loadRagStatus(); }}>
            RAG
          </button>
        </div>
      </div>

      {#if activeTab === "markdown"}
        <SourceEditorPanel
          {selectedPath}
          {loadingFile}
          {sourceDirty}
          {sourceMessage}
          {savingSource}
          {deletingSource}
          {sourceContent}
          {saveSourceFile}
          {resetSourceEdits}
          {deleteSourceFile}
          {canDeleteSelectedSource}
          {updateSourceDraft}
          expandSourceEditor={() => (sourceEditorExpanded = true)}
        />
      {:else if activeTab === "prompt"}
        <div class="starts-settings-row">
          <label class="inline-check">
            <input
              type="checkbox"
              checked={scenarioSettings.prompt_graph_mode === "per_start"}
              onchange={(e) => {
                const mode = e.currentTarget.checked ? "per_start" : "common";
                scenarioSettings = { ...scenarioSettings, prompt_graph_mode: mode };
                if (mode === "per_start" && starts.length && !selectedStartTabId) {
                  selectedStartTabId = starts[0].id;
                }
                void saveScenarioSettings({ prompt_graph_mode: mode });
                if (!starts.length) void loadStarts();
              }}
            />
            <span>{$t("editor.perStartMode")}</span>
          </label>
          {#if settingsMessage}<span class="mini-ok">{settingsMessage}</span>{/if}
          {#if settingsError}<span class="mini-error">{settingsError}</span>{/if}
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
          <div class="prompt-graph-meta">
            <span>graph: {promptGraph.id}</span>
            <span>source: {promptGraphSource || "unknown"}</span>
            <span>version: {promptGraph.version}</span>
            {#if scenarioSettings.prompt_graph_mode === "per_start" && !currentGraphOwnFlag}
              <span class="graph-inherited-notice">{$t("editor.graphInherited")}</span>
            {/if}
            {#if promptGraphDirty}
              <span>unsaved changes</span>
            {/if}
            {#if scenarioSettings.prompt_graph_mode === "per_start" && activeStartId}
              <button class="meta-inline-button" type="button" onclick={() => void openManifestModal(activeStartId)}>
                manifest
              </button>
            {/if}
            <div class="meta-view-toggle">
              <button class:selected={promptView === "table"} type="button" onclick={() => (promptView = "table")}>
                {$t("editor.viewTable")}
              </button>
              <button class:selected={promptView === "visual"} type="button" onclick={() => (promptView = "visual")}>
                {$t("editor.viewVisual")}
              </button>
            </div>
          </div>

          <div class="prompt-editor-actions">
            <button type="button" disabled={savingPromptGraph || !promptGraphDirty} onclick={() => void savePromptGraphRouted()}>
              <Save size={15} aria-hidden="true" /> {savingPromptGraph ? $t("editor.saving") : $t("editor.save")}
            </button>
            <button type="button" disabled={savingPromptGraph} onclick={() => scenarioSettings.prompt_graph_mode === "per_start" && activeStartId ? void loadStartPromptGraph(activeStartId) : void loadPromptGraph()}>
              <RotateCcw size={15} aria-hidden="true" /> {$t("editor.reload")}
            </button>
            {#if starts.length && scenarioSettings.prompt_graph_mode === "common"}
              <button type="button" disabled={duplicatingGraph} onclick={() => { duplicateGraphModal = true; duplicateGraphTargetId = starts[0]?.id || ""; duplicateGraphMessage = ""; duplicateGraphError = ""; }}>
                <Copy size={15} aria-hidden="true" /> {$t("editor.duplicateGraph")}
              </button>
            {/if}
            {#if promptGraphMessage}
              <span>{promptGraphMessage}</span>
            {/if}
          </div>

          {#if promptGraphWarnings.length}
            <div class="notice">
              {#each promptGraphWarnings as warning}
                <div>{warning}</div>
              {/each}
            </div>
          {/if}

          {#if promptView === "table"}
            <div class="prompt-table" role="table" aria-label="Prompt composition">
              <div role="row" class="prompt-row heading">
                <span>order</span>
                <span>node</span>
                <span>type</span>
                <span>source</span>
                <span>role</span>
                <span>required</span>
                <span>budget</span>
                <span>condition</span>
                <span>move</span>
              </div>
              {#each promptNodes() as node, index}
                <div role="row" class="prompt-row">
                  <label>
                    <span class="sr-only">order</span>
                    <input
                      class="compact-input"
                      type="number"
                      value={node.order}
                      onchange={(event) => updateNodeField(index, "order", optionalNumber(event.currentTarget.value) ?? node.order)}
                    />
                  </label>
                  <label>
                    <span class="sr-only">node id</span>
                    <input
                      class="compact-input"
                      type="text"
                      value={node.id}
                      onchange={(e) => {
                        const err = renameNode(index, e.currentTarget.value);
                        if (err) { e.currentTarget.value = node.id; e.currentTarget.setCustomValidity(err); e.currentTarget.reportValidity(); }
                        else { e.currentTarget.setCustomValidity(""); }
                      }}
                    />
                  </label>
                  <label>
                    <span class="sr-only">node type</span>
                    <select class="compact-input" value={node.type}
                      onchange={(e) => changeNodeType(index, node, e.currentTarget.value)}>
                      {#each promptNodeTypes as pt}<option value={pt}>{pt}</option>{/each}
                    </select>
                  </label>
                  {#if node.type === "file"}
                    <label>
                      <span class="sr-only">source</span>
                      <select
                        class="compact-input"
                        value={node.path || ""}
                        onchange={(event) => updateNodeField(index, "path", event.currentTarget.value)}
                      >
                        {#each fileNodePathOptions(node) as path}
                          <option value={path}>{path}</option>
                        {/each}
                      </select>
                    </label>
                  {:else}
                    <span>{nodeSource(node)}</span>
                  {/if}
                  <label>
                    <span class="sr-only">role</span>
                    <select
                      class="compact-input"
                      value={node.role}
                      onchange={(event) => updateNodeField(index, "role", event.currentTarget.value)}
                    >
                      {#each promptRoles as role}
                        <option value={role}>{role}</option>
                      {/each}
                    </select>
                  </label>
                  <label class="inline-check">
                    <input
                      type="checkbox"
                      checked={node.required === true}
                      onchange={(event) => updateNodeField(index, "required", event.currentTarget.checked)}
                    />
                    <span>{node.required ? "yes" : "no"}</span>
                  </label>
                  {#if node.type === "session_log"}
                    <label>
                      <span class="sr-only">budget</span>
                      <input
                        class="compact-input"
                        type="number"
                        min="0"
                        value={node.token_budget ?? ""}
                        placeholder="budget"
                        onchange={(event) => updateNodeField(index, "token_budget", optionalNumber(event.currentTarget.value))}
                      />
                    </label>
                  {:else if node.type === "rag"}
                    <div class="budget-pair">
                      <input
                        class="compact-input"
                        type="number"
                        min="0"
                        value={node.limit ?? ""}
                        placeholder="limit"
                        title="result limit"
                        onchange={(event) => updateNodeField(index, "limit", optionalNumber(event.currentTarget.value))}
                      />
                      <input
                        class="compact-input"
                        type="number"
                        min="0"
                        value={node.token_budget ?? ""}
                        placeholder="tokens"
                        title="token budget"
                        onchange={(event) => updateNodeField(index, "token_budget", optionalNumber(event.currentTarget.value))}
                      />
                    </div>
                  {:else}
                    <span></span>
                  {/if}
                  <label>
                    <span class="sr-only">condition</span>
                    <select
                      class="compact-input"
                      value={conditionMode(node)}
                      title={nodeCondition(node)}
                      onchange={(event) => updateCondition(index, node, event.currentTarget.value)}
                    >
                      <option value="none">none</option>
                      <option value="image_enabled">image enabled</option>
                      <option value="image_disabled">image disabled</option>
                    </select>
                  </label>
                  <span class="row-actions">
                    <button class="icon-button compact-icon" type="button" title={$t("editor.duplicateNode")} onclick={() => duplicateNode(index)}>
                      <Copy size={14} aria-hidden="true" />
                    </button>
                    <button class="icon-button compact-icon" type="button" title={$t("editor.moveUp")} disabled={index === 0} onclick={() => moveNode(index, "up")}>
                      <ArrowUp size={14} aria-hidden="true" />
                    </button>
                    <button
                      class="icon-button compact-icon"
                      type="button"
                      title={$t("editor.moveDown")}
                      disabled={index === promptNodes().length - 1}
                      onclick={() => moveNode(index, "down")}
                    >
                      <ArrowDown size={14} aria-hidden="true" />
                    </button>
                  </span>
                </div>
              {/each}
            </div>

            <PromptPreviewPanel
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
          {:else}
            {#if isMobile}
              <p class="notice">{$t("editor.visualDesktopOnly")}</p>
            {:else}
              <div class="visual-workspace" aria-label="Visual prompt flow">
                <div class="visual-canvas">
                  <SvelteFlow
                    nodes={visualNodes()}
                    edges={visualEdges()}
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
                      <h4>{selectedVisualNode()?.id || (addingNode ? $t("editor.newNode") : $t("editor.noSelection"))}</h4>
                    </div>
                    <div style="display:flex;gap:4px;align-items:center">
                      {#if selectedVisualNode()}
                        <button
                          class="icon-button"
                          type="button"
                          title={$t("editor.duplicateNode")}
                          onclick={() => duplicateNode(selectedVisualNodeIndex())}
                        >
                          <Copy size={15} aria-hidden="true" />
                        </button>
                        <button
                          class="icon-button"
                          type="button"
                          title={$t("editor.deleteNode")}
                          onclick={() => deleteNode(selectedVisualNodeIndex())}
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

                  {#if selectedVisualNode()}
                    {@const node = selectedVisualNode()}
                    {@const idx = selectedVisualNodeIndex()}
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
                        <label class="visual-field">
                          <span class="visual-field-label">token budget</span>
                          <input class="compact-input" type="number" min="0" value={node?.token_budget ?? ""}
                            oninput={(e) => updateNodeField(idx, "token_budget", optionalNumber(e.currentTarget.value))} />
                        </label>
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
                        disabled={idx >= promptNodes().length - 1}
                        onclick={() => moveNode(idx, "down")}
                      >
                        <ArrowDown size={15} aria-hidden="true" /> {$t("editor.moveDown")}
                      </button>
                    </div>
                  {:else if !addingNode}
                    <p class="notice">{$t("editor.nodeSelectHint")}</p>
                  {/if}
                </aside>
              </div>
            {/if}
          {/if}
        {:else}
          <p class="notice">{$t("editor.noGraph")}</p>
        {/if}
      {:else if activeTab === "rag"}
        <div class="rag-status-panel">
          <div class="rag-section">
            <div class="rag-section-header">
              <h4>{$t("editor.keywordIndex")}</h4>
              <div class="rag-actions">
                <button type="button" disabled={rebuildingRagIndex || ragStatusLoading} onclick={() => void doRebuildRagIndex()}>
                  <RotateCcw size={14} aria-hidden="true" /> {rebuildingRagIndex ? $t("editor.rebuilding") : $t("editor.rebuild")}
                </button>
              </div>
            </div>
            {#if ragStatusLoading}
              <p class="notice">{$t("editor.loadingStatus")}</p>
            {:else if ragStatusError}
              <p class="notice error-notice">{ragStatusError}</p>
            {:else if ragStatus}
              <dl class="rag-dl">
                <dt>{$t("editor.indexLabel")}</dt>
                <dd>{ragStatus.rag_index?.indexed ? $t("editor.yes") : $t("editor.no")}</dd>
                <dt>{$t("editor.countLabel")}</dt>
                <dd>{ragStatus.rag_index?.document_count ?? 0}</dd>
                <dt>{$t("editor.updatedAt")}</dt>
                <dd>{ragStatus.rag_index?.indexed_at || "—"}</dd>
                <dt>{$t("editor.rebuildNeededLabel")}</dt>
                <dd class:rag-warn={ragStatus.rag_index?.rebuild_needed}>{ragStatus.rag_index?.rebuild_needed ? $t("editor.rebuildYes") : $t("editor.rebuildNo")}</dd>
                <dt>{$t("editor.memoryCount")}</dt>
                <dd>{ragStatus.memory?.total ?? 0}</dd>
              </dl>
            {:else}
              <p class="notice">{$t("editor.ragStatusNotLoaded")}</p>
            {/if}
            {#if ragRebuildMessage}
              <p class="rag-message">{ragRebuildMessage}</p>
            {/if}
          </div>

          <div class="rag-section">
            <div class="rag-section-header">
              <h4>{$t("editor.vectorIndex")}</h4>
              <div class="rag-actions">
                <button
                  type="button"
                  disabled={rebuildingVectorIndex || vectorStatusLoading || !vectorStatus?.embedding?.enabled}
                  title={vectorStatus?.embedding?.enabled ? "" : $t("editor.embeddingDisabled")}
                  onclick={() => void doRebuildVectorIndex()}
                >
                  <RotateCcw size={14} aria-hidden="true" /> {rebuildingVectorIndex ? $t("editor.rebuilding") : $t("editor.rebuild")}
                </button>
              </div>
            </div>
            {#if vectorStatusLoading}
              <p class="notice">{$t("editor.loadingStatus")}</p>
            {:else if vectorStatusError}
              <p class="notice error-notice">{vectorStatusError}</p>
            {:else if vectorStatus}
              <dl class="rag-dl">
                <dt>Embedding</dt>
                <dd class:rag-disabled={!vectorStatus.embedding?.enabled}>
                  {vectorStatus.embedding?.enabled ? `Enabled (${vectorStatus.embedding.model})` : $t("editor.embeddingDisabled")}
                </dd>
                <dt>{$t("editor.indexLabel")}</dt>
                <dd>{vectorStatus.vector_index?.indexed ? $t("editor.yes") : $t("editor.no")}</dd>
                {#if vectorStatus.vector_index?.indexed}
                  <dt>{$t("editor.modelLabel")}</dt>
                  <dd>{vectorStatus.vector_index.model}</dd>
                  <dt>{$t("editor.countLabel")}</dt>
                  <dd>{vectorStatus.vector_index.document_count}</dd>
                  <dt>{$t("editor.updatedAt")}</dt>
                  <dd>{vectorStatus.vector_index.indexed_at || "—"}</dd>
                  <dt>{$t("editor.rebuildNeededLabel")}</dt>
                  <dd class:rag-warn={vectorStatus.vector_index?.rebuild_needed}>{vectorStatus.vector_index?.rebuild_needed ? $t("editor.rebuildYes") : $t("editor.rebuildNo")}</dd>
                {/if}
              </dl>
            {:else}
              <p class="notice">{$t("editor.vectorStatusNotLoaded")}</p>
            {/if}
            {#if vectorRebuildMessage}
              <p class="rag-message">{vectorRebuildMessage}</p>
            {/if}
          </div>
        </div>
      {/if}
    </section>
  </div>
{/if}

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

{#if createFileModalOpen}
  <div class="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="create-source-modal-heading">
    <button class="modal-scrim" type="button" aria-label={$t("common.close")} onclick={() => { createFileModalOpen = false; newSourceError = ""; }}></button>
    <div class="picker-modal create-source-modal">
      <div class="panel-header compact">
        <h3 id="create-source-modal-heading"><FilePlus2 size={16} aria-hidden="true" /> {$t("editor.newFile")}</h3>
        <button class="icon-button" type="button" title={$t("common.close")} onclick={() => { createFileModalOpen = false; newSourceError = ""; }}>
          <X size={18} aria-hidden="true" />
        </button>
      </div>

      <label>
        <span>Type</span>
        <select bind:value={newSourceKind}>
          <option value="characters">Character</option>
          <option value="lore">Lore</option>
          <option value="startings">Starting</option>
          <option value="gm">GM prompt</option>
        </select>
      </label>
      <label>
        <span>ID</span>
        <input bind:value={newSourceId} placeholder="alice" />
      </label>
      <label>
        <span>Name</span>
        <input bind:value={newSourceName} placeholder={$t("editor.displayName")} />
      </label>
      <small class="source-path-preview">{newSourcePath() || `${newSourceKind}/<id>.md`}</small>

      {#if sourceDirty}
        <p class="mini-error">{$t("editor.unsavedCreateWarning")}</p>
      {:else if newSourceError}
        <p class="mini-error">{newSourceError}</p>
      {/if}

      <div class="modal-row-actions">
        <button
          type="button"
          disabled={creatingSource || sourceDirty || !newSourceId.trim()}
          onclick={() => void createSourceFile()}
        >
          <FilePlus2 size={15} aria-hidden="true" /> {creatingSource ? $t("common.creating") : $t("common.create")}
        </button>
        <button type="button" onclick={() => { createFileModalOpen = false; newSourceError = ""; }}>{$t("common.cancel")}</button>
      </div>
    </div>
  </div>
{/if}

{#if sourceEditorExpanded}
  <div class="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="source-expand-modal-heading">
    <button class="modal-scrim" type="button" aria-label={$t("common.close")} onclick={() => (sourceEditorExpanded = false)}></button>
    <div class="picker-modal source-editor-modal">
      <div class="panel-header compact">
        <h3 id="source-expand-modal-heading"><FilePenLine size={16} aria-hidden="true" /> {selectedPath || "No file"}</h3>
        <div class="source-editor-modal-actions">
          <button
            type="button"
            disabled={savingSource || !sourceDirty}
            onclick={() => void saveSourceFile()}
          >
            <Save size={15} aria-hidden="true" /> {savingSource ? $t("editor.saving") : $t("editor.save")}
          </button>
          <button
            class="icon-button"
            type="button"
            title={$t("common.close")}
            onclick={() => (sourceEditorExpanded = false)}
          >
            <Minimize2 size={18} aria-hidden="true" />
          </button>
        </div>
      </div>
      {#if sourceDirty}
        <div class="prompt-graph-meta"><span>unsaved changes</span></div>
      {/if}
      {#if sourceMessage}
        <div class="prompt-graph-meta"><span>{sourceMessage}</span></div>
      {/if}
      <textarea
        class="source-editor"
        value={sourceContent}
        spellcheck="false"
        oninput={updateSourceDraft}
      ></textarea>
    </div>
  </div>
{/if}

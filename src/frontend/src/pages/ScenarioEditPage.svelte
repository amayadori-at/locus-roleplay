<script>
  import { ArrowLeft, ArrowDown, ArrowUp, FilePenLine, FilePlus2, GitBranch, ListTree, Minimize2, Plus, RotateCcw, Save, Trash2, X } from "lucide-svelte";
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
    getScenarioSourceFile,
    listPersonas,
    listProfiles,
    listScenarioSessions,
    listScenarioSourceFiles,
    rebuildScenarioRagIndex,
    rebuildScenarioVectorIndex,
    updateScenarioSourceFile,
    updateScenarioPromptGraph
  } from "../lib/api.js";
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
  let previewUserMessage = "プレビュー用のユーザー入力です。";
  let selectedVisualNodeId = "";
  /** @type {Array<string>} */
  let promptGraphWarnings = [];
  const promptRoles = ["system", "user", "assistant", "messages"];
  const promptNodeTypes = ["file", "selected_persona", "state", "rag", "session_log", "user_note", "current_user_message", "condition", "output"];

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
      error = "scenario が指定されていません。";
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
      await Promise.all([loadPromptGraph(), loadPreviewChoices()]);
    } catch (caught) {
      error = caught instanceof Error ? caught.message : "シナリオファイル一覧を読み込めませんでした。";
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
      error = caught instanceof Error ? caught.message : "シナリオファイルを読み込めませんでした。";
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
      sourceMessage = "保存しました。";
      files = files.map((file) => (file.path === selectedPath ? { ...file, size: content.length } : file));
    } catch (caught) {
      error = caught instanceof Error ? caught.message : "シナリオファイルを保存できませんでした。";
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
    if (!window.confirm(`${pathToDelete} を削除します。元に戻せません。`)) {
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
        sourceMessage = `${pathToDelete} を削除しました。`;
      } else {
        selectedPath = "";
        content = "";
        sourceContent = "";
        sourceDirty = false;
        sourceMessage = `${pathToDelete} を削除しました。`;
      }
      await loadPromptGraph();
    } catch (caught) {
      error = caught instanceof Error ? caught.message : "シナリオファイルを削除できませんでした。";
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
      return `---\ntype: starting\nid: ${id}\nname: ${name}\n---\n\n${name}から物語が始まります。\n`;
    }
    return `---\ntype: gm_prompt\nid: ${id}\n---\n\n# ${name}\n\n`;
  }

  function validateNewSourceInput() {
    const id = newSourceId.trim();
    if (!/^[A-Za-z0-9_-]+$/.test(id)) {
      return "ID は半角英数字、underscore、hyphen のみで入力してください。";
    }
    if (files.some((file) => file.path === newSourcePath())) {
      return "同じ path のファイルが既に存在します。";
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
      sourceMessage = "新規ファイルを作成しました。";
    } catch (caught) {
      newSourceError = caught instanceof Error ? caught.message : "新規ファイルを作成できませんでした。";
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
      promptGraphError = caught instanceof Error ? caught.message : "Prompt Graph を読み込めませんでした。";
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
      promptPreviewError = caught instanceof Error ? caught.message : "Preview条件を読み込めませんでした。";
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
      promptGraphMessage = "Prompt Graph を保存しました。";
    } catch (caught) {
      promptGraphError = caught instanceof Error ? caught.message : "Prompt Graph を保存できませんでした。";
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
      promptPreviewError = caught instanceof Error ? caught.message : "Prompt Preview を生成できませんでした。";
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

  /** @param {string} type */
  function defaultRoleForType(type) {
    if (type === "current_user_message") return "user";
    if (type === "session_log") return "messages";
    return "system";
  }

  function submitAddNode() {
    newNodeError = "";
    const id = newNodeId.trim();
    if (!id) { newNodeError = "id は必須です"; return; }
    if (!/^[a-z0-9_]+$/.test(id)) { newNodeError = "id は英小文字・数字・_ のみ使用できます"; return; }
    if (promptNodes().some((n) => n.id === id)) { newNodeError = `id "${id}" は既に存在します`; return; }
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
      ragStatusError = caught instanceof Error ? caught.message : "RAG ステータスを読み込めませんでした。";
    } finally {
      ragStatusLoading = false;
    }
    try {
      vectorStatus = await getScenarioRagVectorStatus(route.scenarioId);
    } catch (caught) {
      vectorStatusError = caught instanceof Error ? caught.message : "ベクターインデックス情報を読み込めませんでした。";
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
      ragRebuildMessage = `リビルド完了 (${result.index?.document_count ?? 0} 件)`;
      ragStatus = await getScenarioRagStatus(route.scenarioId);
    } catch (caught) {
      ragRebuildMessage = caught instanceof Error ? caught.message : "リビルドに失敗しました。";
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
      vectorRebuildMessage = `リビルド完了 (${result.index?.document_count ?? 0} 件、モデル: ${result.index?.model ?? ""})`;
      vectorStatus = await getScenarioRagVectorStatus(route.scenarioId);
    } catch (caught) {
      vectorRebuildMessage = caught instanceof Error ? caught.message : "ベクターインデックスのリビルドに失敗しました。";
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
  <p class="notice">シナリオファイルを読み込んでいます。</p>
{:else}
  <div class="editor-layout">
    <aside class="panel source-tree" aria-labelledby="source-tree-heading">
      <div class="source-tree-header">
        <h3 id="source-tree-heading"><ListTree size={18} aria-hidden="true" /> Vault Tree</h3>
        <button
          class="icon-button compact-icon"
          type="button"
          title="新規ファイル作成"
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
                title={sourceDirty ? "未保存変更を保存または破棄してください" : file.path}
                onclick={() => loadFile(file.path)}
              >
                <strong>{file.path}</strong>
                <span>{file.size || 0} bytes</span>
              </button>
            </li>
          {/each}
        </ul>
      {:else}
        <p>閲覧可能なファイルがありません。</p>
      {/if}
    </aside>

    <section class="panel editor-panel" aria-labelledby="editor-heading">
      <div class="panel-header compact">
        <h3 id="editor-heading"><FilePenLine size={18} aria-hidden="true" /> {selectedPath || "No file"}</h3>
        <div class="segmented-control">
          <button class:selected={activeTab === "markdown"} type="button" onclick={() => (activeTab = "markdown")}>
            Markdown
          </button>
          <button class:selected={activeTab === "prompt"} type="button" onclick={() => (activeTab = "prompt")}>
            Prompt
          </button>
          <button class:selected={activeTab === "visual"} type="button" onclick={() => (activeTab = "visual")}>
            Visual
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
        {#if loadingPromptGraph}
          <p class="notice">Prompt Graph を読み込んでいます。</p>
        {:else if promptGraphError}
          <p class="notice error-notice">{promptGraphError}</p>
        {:else if promptGraph}
          <div class="prompt-graph-meta">
            <span>graph: {promptGraph.id}</span>
            <span>source: {promptGraphSource || "unknown"}</span>
            <span>version: {promptGraph.version}</span>
            {#if promptGraphDirty}
              <span>unsaved changes</span>
            {/if}
          </div>

          <div class="prompt-editor-actions">
            <button type="button" disabled={savingPromptGraph || !promptGraphDirty} onclick={() => void savePromptGraph()}>
              <Save size={15} aria-hidden="true" /> {savingPromptGraph ? "保存中" : "保存"}
            </button>
            <button type="button" disabled={savingPromptGraph} onclick={() => void loadPromptGraph()}>
              <RotateCcw size={15} aria-hidden="true" /> 再読込
            </button>
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
                <span>{node.id}</span>
                <span>{node.type}</span>
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
                  <button class="icon-button compact-icon" type="button" title="上へ" disabled={index === 0} onclick={() => moveNode(index, "up")}>
                    <ArrowUp size={14} aria-hidden="true" />
                  </button>
                  <button
                    class="icon-button compact-icon"
                    type="button"
                    title="下へ"
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
          <p class="notice">Prompt Graph がありません。</p>
        {/if}
      {:else if activeTab === "rag"}
        <div class="rag-status-panel">
          <div class="rag-section">
            <div class="rag-section-header">
              <h4>キーワードインデックス</h4>
              <div class="rag-actions">
                <button type="button" disabled={rebuildingRagIndex || ragStatusLoading} onclick={() => void doRebuildRagIndex()}>
                  <RotateCcw size={14} aria-hidden="true" /> {rebuildingRagIndex ? "リビルド中…" : "リビルド"}
                </button>
              </div>
            </div>
            {#if ragStatusLoading}
              <p class="notice">読み込み中…</p>
            {:else if ragStatusError}
              <p class="notice error-notice">{ragStatusError}</p>
            {:else if ragStatus}
              <dl class="rag-dl">
                <dt>インデックス</dt>
                <dd>{ragStatus.rag_index?.indexed ? "あり" : "なし"}</dd>
                <dt>件数</dt>
                <dd>{ragStatus.rag_index?.document_count ?? 0}</dd>
                <dt>更新日時</dt>
                <dd>{ragStatus.rag_index?.indexed_at || "—"}</dd>
                <dt>要リビルド</dt>
                <dd class:rag-warn={ragStatus.rag_index?.rebuild_needed}>{ragStatus.rag_index?.rebuild_needed ? "はい" : "なし"}</dd>
                <dt>Memory 件数</dt>
                <dd>{ragStatus.memory?.total ?? 0}</dd>
              </dl>
            {:else}
              <p class="notice">RAG ステータスを読み込んでいません。</p>
            {/if}
            {#if ragRebuildMessage}
              <p class="rag-message">{ragRebuildMessage}</p>
            {/if}
          </div>

          <div class="rag-section">
            <div class="rag-section-header">
              <h4>ベクターインデックス</h4>
              <div class="rag-actions">
                <button
                  type="button"
                  disabled={rebuildingVectorIndex || vectorStatusLoading || !vectorStatus?.embedding?.enabled}
                  title={vectorStatus?.embedding?.enabled ? "" : "Embedding が設定されていません"}
                  onclick={() => void doRebuildVectorIndex()}
                >
                  <RotateCcw size={14} aria-hidden="true" /> {rebuildingVectorIndex ? "リビルド中…" : "リビルド"}
                </button>
              </div>
            </div>
            {#if vectorStatusLoading}
              <p class="notice">読み込み中…</p>
            {:else if vectorStatusError}
              <p class="notice error-notice">{vectorStatusError}</p>
            {:else if vectorStatus}
              <dl class="rag-dl">
                <dt>Embedding</dt>
                <dd class:rag-disabled={!vectorStatus.embedding?.enabled}>
                  {vectorStatus.embedding?.enabled ? `有効 (${vectorStatus.embedding.model})` : "無効（LOCUS_EMBEDDING_MODEL 未設定）"}
                </dd>
                <dt>インデックス</dt>
                <dd>{vectorStatus.vector_index?.indexed ? "あり" : "なし"}</dd>
                {#if vectorStatus.vector_index?.indexed}
                  <dt>モデル</dt>
                  <dd>{vectorStatus.vector_index.model}</dd>
                  <dt>件数</dt>
                  <dd>{vectorStatus.vector_index.document_count}</dd>
                  <dt>更新日時</dt>
                  <dd>{vectorStatus.vector_index.indexed_at || "—"}</dd>
                  <dt>要リビルド</dt>
                  <dd class:rag-warn={vectorStatus.vector_index?.rebuild_needed}>{vectorStatus.vector_index?.rebuild_needed ? "はい" : "なし"}</dd>
                {/if}
              </dl>
            {:else}
              <p class="notice">ベクターステータスを読み込んでいません。</p>
            {/if}
            {#if vectorRebuildMessage}
              <p class="rag-message">{vectorRebuildMessage}</p>
            {/if}
          </div>
        </div>
      {:else}
        {#if isMobile}
          <p class="notice">Visual ビューはデスクトップでご確認ください。スマートフォン向けのフロー図表示には対応していません。</p>
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
                <h4>{selectedVisualNode()?.id || (addingNode ? "新規追加" : "未選択")}</h4>
              </div>
              <div style="display:flex;gap:4px;align-items:center">
                {#if selectedVisualNode()}
                  <button
                    class="icon-button"
                    type="button"
                    title="このノードを削除"
                    onclick={() => deleteNode(selectedVisualNodeIndex())}
                  >
                    <Trash2 size={15} aria-hidden="true" />
                  </button>
                {/if}
                <button
                  class="icon-button"
                  type="button"
                  title="ノードを追加"
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
                  <button type="button" class="primary-button" onclick={submitAddNode}>追加</button>
                  <button type="button" onclick={() => { addingNode = false; newNodeError = ""; }}>キャンセル</button>
                </div>
              </div>
            {/if}

            {#if selectedVisualNode()}
              {@const node = selectedVisualNode()}
              {@const idx = selectedVisualNodeIndex()}
              <div class="visual-node-edit">
                <div class="visual-field">
                  <span class="visual-field-label">type</span>
                  <span class="visual-field-value">{node?.type}</span>
                </div>
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
                    <option value="none">なし</option>
                    <option value="image_enabled">画像ON時のみ</option>
                    <option value="image_disabled">画像OFF時のみ</option>
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
                  <ArrowUp size={15} aria-hidden="true" /> 上へ
                </button>
                <button
                  type="button"
                  disabled={idx >= promptNodes().length - 1}
                  onclick={() => moveNode(idx, "down")}
                >
                  <ArrowDown size={15} aria-hidden="true" /> 下へ
                </button>
              </div>
            {:else if !addingNode}
              <p class="notice">ノードをクリックして選択、＋で新規追加します。</p>
            {/if}
          </aside>
        </div>
        {/if}
      {/if}
    </section>
  </div>
{/if}

{#if createFileModalOpen}
  <div class="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="create-source-modal-heading">
    <button class="modal-scrim" type="button" aria-label="閉じる" onclick={() => { createFileModalOpen = false; newSourceError = ""; }}></button>
    <div class="picker-modal create-source-modal">
      <div class="panel-header compact">
        <h3 id="create-source-modal-heading"><FilePlus2 size={16} aria-hidden="true" /> 新規ファイル作成</h3>
        <button class="icon-button" type="button" title="閉じる" onclick={() => { createFileModalOpen = false; newSourceError = ""; }}>
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
        <input bind:value={newSourceName} placeholder="表示名" />
      </label>
      <small class="source-path-preview">{newSourcePath() || `${newSourceKind}/<id>.md`}</small>

      {#if sourceDirty}
        <p class="mini-error">未保存変更を保存または破棄してから作成してください。</p>
      {:else if newSourceError}
        <p class="mini-error">{newSourceError}</p>
      {/if}

      <div class="modal-row-actions">
        <button
          type="button"
          disabled={creatingSource || sourceDirty || !newSourceId.trim()}
          onclick={() => void createSourceFile()}
        >
          <FilePlus2 size={15} aria-hidden="true" /> {creatingSource ? "作成中" : "作成"}
        </button>
        <button type="button" onclick={() => { createFileModalOpen = false; newSourceError = ""; }}>キャンセル</button>
      </div>
    </div>
  </div>
{/if}

{#if sourceEditorExpanded}
  <div class="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="source-expand-modal-heading">
    <button class="modal-scrim" type="button" aria-label="閉じる" onclick={() => (sourceEditorExpanded = false)}></button>
    <div class="picker-modal source-editor-modal">
      <div class="panel-header compact">
        <h3 id="source-expand-modal-heading"><FilePenLine size={16} aria-hidden="true" /> {selectedPath || "No file"}</h3>
        <div class="source-editor-modal-actions">
          <button
            type="button"
            disabled={savingSource || !sourceDirty}
            onclick={() => void saveSourceFile()}
          >
            <Save size={15} aria-hidden="true" /> {savingSource ? "保存中" : "保存"}
          </button>
          <button
            class="icon-button"
            type="button"
            title="閉じる"
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

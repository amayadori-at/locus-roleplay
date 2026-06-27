<script>
  import { ArrowLeft, Database, FilePenLine, FilePlus2, Minimize2, Network, Save, X } from "lucide-svelte";
  import { onMount, tick } from "svelte";
  import {
    createScenarioSourceFile,
    deleteScenarioSourceFile,
    getScenarioSourceFile,
    listPersonas,
    listProfiles,
    listScenarioSessions,
    listScenarioSourceFiles,
    updateScenarioSourceFile
  } from "../lib/api.js";
  import { t, translateNow } from "../lib/i18n.js";
  import SourceEditorPanel from "../lib/SourceEditorPanel.svelte";
  import KnowledgeTab from "../lib/scenario-edit/KnowledgeTab.svelte";
  import PromptTab from "../lib/scenario-edit/PromptTab.svelte";
  import SourceTreePanel from "../lib/scenario-edit/SourceTreePanel.svelte";
  import { insertLocusRagTag, upsertFrontmatterFields } from "../lib/sourceEditorTools.js";

  /** @type {{
   *   route: { scenarioId?: string, mode?: string, query?: Record<string, string> },
   *   onNavigate?: { openHome?: () => void },
   * }} */
  let { route, onNavigate = {
    openHome: () => {}
  } } = $props();

  /** @type {Array<{ path: string, size?: number }>} */
  let files = $state([]);
  let selectedPath = $state("");
  let sourceFilter = $state("");
  /** @type {Record<string, boolean>} */
  let sourceGroupOpen = $state({});
  let content = $state("");
  let sourceContent = $state("");
  let sourceDirty = $state(false);
  let savingSource = $state(false);
  let deletingSource = $state(false);
  let sourceMessage = $state("");
  let creatingSource = $state(false);
  let newSourceKind = $state("characters");
  let newSourceId = $state("");
  let newSourceName = $state("");
  let newSourceTemplateKind = $state("default");
  let newSourceError = $state("");
  let loading = $state(true);
  let loadingFile = $state(false);
  let loadingPreviewChoices = $state(false);
  let error = $state("");
  let promptPreviewError = $state("");
  let activeTab = $state("markdown");
  /** @type {Array<Record<string, any>>} */
  let sessions = $state([]);
  /** @type {Array<Record<string, any>>} */
  let personas = $state([]);
  /** @type {Array<Record<string, any>>} */
  let profiles = $state([]);
  let previewSessionId = $state("");
  let previewPersonaId = $state("");
  let previewProfileId = $state("");
  let previewUserMessage = $state(translateNow("editor.previewUserInput"));
  let createFileModalOpen = $state(false);
  let sourceEditorExpanded = $state(false);
  let isMobile = $state(false);


  /** Prompt tab component instance (always mounted, hidden when inactive). @type {any} */
  let promptTab = $state(null);
  /** Knowledge tab component instance (always mounted, hidden when inactive). @type {any} */
  let knowledgeTab = $state(null);
  let consolidationSessionId = $state("");
  let consolidationProfileId = $state("");

  const groupedSourceFiles = $derived(groupSourceFiles(files, sourceFilter));
  onMount(async () => {
    const mq = window.matchMedia("(max-width: 860px)");
    isMobile = mq.matches;
    mq.addEventListener("change", (e) => { isMobile = e.matches; });
    hydrateSourceGroupOpen();
    await loadFiles();
    // The tab components mount once loading is false; wait a tick before the
    // initial prompt workspace load so the PromptTab ref exists.
    await tick();
    await promptTab?.loadPromptWorkspace();
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
      ensureSourceGroupOpen(selectedPath);
      if (selectedPath) {
        await loadFile(selectedPath);
      }
      await loadPreviewChoices();
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
    ensureSourceGroupOpen(path);
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
    if (sourceDirty) {
      sourceMessage = translateNow("editor.unsavedDeleteWarning");
      return;
    }
    if (!route.scenarioId || !selectedPath || deletingSource || !canDeleteSelectedSource()) {
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
      await promptTab?.handleSourceDeleted(isStart);
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

  const sourceGroupOrder = [
    { id: "core", labelKey: "editor.sourceGroupCore" },
    { id: "gm", labelKey: "editor.sourceGroupGm" },
    { id: "characters", labelKey: "editor.sourceGroupCharacters" },
    { id: "lore", labelKey: "editor.sourceGroupLore" },
    { id: "startings", labelKey: "editor.sourceGroupStartings" },
    { id: "memory", labelKey: "editor.sourceGroupMemory" },
    { id: "other", labelKey: "editor.sourceGroupOther" }
  ];

  function defaultSourceGroupOpen() {
    return {
      core: true,
      gm: true,
      characters: true,
      lore: true,
      startings: true,
      memory: false,
      other: true
    };
  }

  function sourceGroupStorageKey() {
    return `locus_source_groups_${route.scenarioId || "global"}`;
  }

  function hydrateSourceGroupOpen() {
    sourceGroupOpen = defaultSourceGroupOpen();
    try {
      const raw = window.localStorage.getItem(sourceGroupStorageKey());
      const parsed = raw ? JSON.parse(raw) : null;
      if (parsed && typeof parsed === "object") {
        sourceGroupOpen = { ...sourceGroupOpen, ...parsed };
      }
    } catch {
      sourceGroupOpen = defaultSourceGroupOpen();
    }
  }

  function saveSourceGroupOpen() {
    try {
      window.localStorage.setItem(sourceGroupStorageKey(), JSON.stringify(sourceGroupOpen));
    } catch {
      // localStorage may be unavailable in private contexts; the UI can still work without persistence.
    }
  }

  /** @param {string} path */
  function sourceGroupId(path) {
    if (path === "scenario.md" || path === "system_prompt.md") return "core";
    const top = path.split("/")[0] || "";
    if (["gm", "characters", "lore", "startings", "memory"].includes(top)) return top;
    return "other";
  }

  /**
   * @param {Array<{ path: string, size?: number }>} sourceFiles
   * @param {string} filterText
   */
  function groupSourceFiles(sourceFiles, filterText) {
    const normalizedFilter = filterText.trim().toLowerCase();
    /** @type {Record<string, Array<{ path: string, size?: number }>>} */
    const buckets = {};
    for (const group of sourceGroupOrder) {
      buckets[group.id] = [];
    }
    for (const file of sourceFiles) {
      if (normalizedFilter && !file.path.toLowerCase().includes(normalizedFilter)) {
        continue;
      }
      const groupId = sourceGroupId(file.path);
      buckets[groupId]?.push(file);
    }
    return sourceGroupOrder
      .map((group) => ({ ...group, files: buckets[group.id] || [] }))
      .filter((group) => group.files.length > 0 || (!normalizedFilter && ["gm", "characters", "lore", "startings"].includes(group.id)));
  }

  /**
   * @param {string} groupId
   * @param {Record<string, boolean>} openState
   */
  function isSourceGroupOpen(groupId, openState = sourceGroupOpen) {
    return openState[groupId] !== false;
  }

  /** @param {string} groupId */
  function toggleSourceGroup(groupId) {
    sourceGroupOpen = { ...sourceGroupOpen, [groupId]: !isSourceGroupOpen(groupId, sourceGroupOpen) };
    saveSourceGroupOpen();
  }

  /** @param {string} path */
  function ensureSourceGroupOpen(path) {
    if (!path) return;
    const groupId = sourceGroupId(path);
    if (sourceGroupOpen[groupId] === false) {
      sourceGroupOpen = { ...sourceGroupOpen, [groupId]: true };
      saveSourceGroupOpen();
    }
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
      return `---\ntype: character\nid: ${id}\nname: ${name}\naliases:\ntags:\nkeywords:\n---\n\n# ${name}\n\n## Personality\n\n## Appearance\n\n## Speaking Style\n\n## Notes\n\n`;
    }
    if (newSourceKind === "lore") {
      const locusExample = newSourceTemplateKind === "locus_rag"
        ? `\n<locus-rag keywords="${name}" priority="10">\nここに検索対象にしたい設定本文を記述します。\n</locus-rag>\n`
        : "";
      return `---\ntype: lore\nid: ${id}\ntitle: ${name}\ntags:\nkeywords:\npriority: 0\nkeywords_enabled: false\n---\n\n# ${name}\n\n## Overview\n\n## Details\n${locusExample}`;
    }
    if (newSourceKind === "startings") {
      return `---\ntype: starting\nid: ${id}\nname: ${name}\n---\n\n${translateNow("editor.startingTemplate", { name })}`;
    }
    return `---\ntype: gm_prompt\nid: ${id}\ntitle: ${name}\n---\n\n# ${name}\n\n## Policy\n\n## Style\n\n## Constraints\n\n`;
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
      const createdKind = newSourceKind;
      const createdId = newSourceId.trim();
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
      if (createdKind === "startings") {
        await promptTab?.handleStartCreated(createdId);
      }
    } catch (caught) {
      newSourceError = caught instanceof Error ? caught.message : translateNow("editor.createFileError");
    } finally {
      creatingSource = false;
    }
  }

  /** @param {string} [kind] */
  function openCreateFileModal(kind = "") {
    if (["gm", "characters", "lore", "startings"].includes(kind)) {
      newSourceKind = kind;
    }
    newSourceTemplateKind = "default";
    createFileModalOpen = true;
    newSourceError = "";
  }

  /** @param {Record<string, any>} fields */
  function applyFrontmatterFields(fields) {
    sourceContent = upsertFrontmatterFields(sourceContent, fields);
    sourceDirty = sourceContent !== content;
    sourceMessage = "";
  }

  /**
   * @param {number} start
   * @param {number} end
   * @param {Record<string, any>} attrs
   */
  function insertLocusRag(start, end, attrs) {
    const result = insertLocusRagTag(sourceContent, start, end, attrs);
    sourceContent = result.content;
    sourceDirty = sourceContent !== content;
    sourceMessage = "";
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
      previewProfileId = profiles.filter((profile) => profile.kind === "roleplay")[0]?.id || profiles[0]?.id || "";
      consolidationSessionId = previewSessionId;
      consolidationProfileId = profiles.find((profile) => profile.kind === "memory_summary")?.id || profiles[0]?.id || "";
    } catch (caught) {
      promptPreviewError = caught instanceof Error ? caught.message : translateNow("editor.loadPreviewError");
    } finally {
      loadingPreviewChoices = false;
    }
  }


  /** @param {string} path */
  async function openMemorySource(path) {
    if (!path) return;
    await loadFile(path);
    sourceGroupOpen.memory = true;
    activeTab = "markdown";
  }


</script>

<div class="toolbar">
  <div>
    <p class="eyebrow">Scenario</p>
    <h2 id="workspace-heading">{route.scenarioId || "Scenario Page"}</h2>
  </div>
  <div class="toolbar-actions">
    <button class="icon-button" type="button" title="Front Page" onclick={onNavigate.openHome}>
      <ArrowLeft size={18} aria-hidden="true" />
    </button>
  </div>
</div>

{#if error}
  <p class="notice error-notice">{error}</p>
{/if}

{#if loading}
  <p class="notice">{$t("editor.loadingFiles")}</p>
{:else}
  <div class="editor-layout">
    {#snippet editorTabBar()}
      <h3 id="editor-heading">
        {#if activeTab === "markdown"}
          <FilePenLine size={18} aria-hidden="true" /> {selectedPath || "No file"}
        {:else if activeTab === "prompt"}
          <Network size={18} aria-hidden="true" /> Prompt Graph
        {:else}
          <Database size={18} aria-hidden="true" /> Knowledge
        {/if}
      </h3>
      <div class="segmented-control">
        <button class:selected={activeTab === "markdown"} type="button" onclick={() => (activeTab = "markdown")}>
          Markdown
        </button>
        <button class:selected={activeTab === "prompt"} type="button" onclick={() => { activeTab = "prompt"; void promptTab?.ensureStartsLoaded(); }}>
          Prompt
        </button>
        <button class:selected={activeTab === "knowledge"} type="button" onclick={() => { activeTab = "knowledge"; void knowledgeTab?.loadRagStatus(); void knowledgeTab?.loadMemory(); void knowledgeTab?.loadConsolidationSuggestions(); }}>
          Knowledge
        </button>
      </div>
    {/snippet}

    {#if isMobile}
      <div class="panel-header compact mobile-editor-tabs">
        {@render editorTabBar()}
      </div>
    {/if}

    <SourceTreePanel
      hidden={activeTab !== "markdown"}
      {files}
      {groupedSourceFiles}
      {sourceGroupOpen}
      bind:sourceFilter
      {selectedPath}
      {sourceDirty}
      {loadFile}
      {toggleSourceGroup}
      {openCreateFileModal}
    />

    <section class="panel editor-panel" aria-labelledby="editor-heading">
      {#if !isMobile}
        <div class="panel-header compact">
          {@render editorTabBar()}
        </div>
      {/if}

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
          {applyFrontmatterFields}
          {insertLocusRag}
          expandSourceEditor={() => (sourceEditorExpanded = true)}
        />
      {/if}

      <PromptTab
        bind:this={promptTab}
        scenarioId={route.scenarioId || ""}
        hidden={activeTab !== "prompt"}
        {files}
        {sessions}
        {personas}
        {profiles}
        {loadingPreviewChoices}
        {isMobile}
        bind:promptPreviewError
        bind:previewSessionId
        bind:previewPersonaId
        bind:previewProfileId
        bind:previewUserMessage
      />

      <KnowledgeTab
        bind:this={knowledgeTab}
        scenarioId={route.scenarioId || ""}
        hidden={activeTab !== "knowledge"}
        {sessions}
        {profiles}
        bind:consolidationSessionId
        bind:consolidationProfileId
        openSource={openMemorySource}
      />
    </section>
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
      <label>
        <span>Template</span>
        <select bind:value={newSourceTemplateKind}>
          <option value="default">Default</option>
          <option value="locus_rag" disabled={newSourceKind !== "lore"}>Lore with &lt;locus-rag&gt;</option>
        </select>
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

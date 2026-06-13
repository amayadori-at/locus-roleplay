<script>
  import { CircleCheck, FilePenLine, RotateCcw, Save, Trash2, X } from "lucide-svelte";
  import {
    applyMemoryConsolidationSuggestion,
    createMemoryConsolidationSuggestions,
    deleteMemory,
    listScenarioMemory,
    getScenarioRagStatus,
    getScenarioRagVectorStatus,
    listMemoryConsolidationSuggestions,
    rebuildScenarioRagIndex,
    rebuildScenarioVectorIndex,
    updateMemoryMetadata,
    updateMemoryConsolidationSuggestionStatus
  } from "../api.js";
  import { t, translateNow } from "../i18n.js";
  import { buildMemoryFilterOptions, memoryMatchesFilters as memoryItemMatchesFilters } from "../memoryReview.js";

  /** @type {{
   *   scenarioId?: string,
   *   hidden?: boolean,
   *   sessions?: Array<Record<string, any>>,
   *   profiles?: Array<Record<string, any>>,
   *   consolidationSessionId?: string,
   *   consolidationProfileId?: string,
   *   openSource?: (path: string) => Promise<void>,
   * }} */
  let {
    scenarioId = "",
    hidden = false,
    sessions = [],
    profiles = [],
    // Bound to the page so loadPreviewChoices can set the initial values.
    consolidationSessionId = $bindable(""),
    consolidationProfileId = $bindable(""),
    openSource = async (_path) => {}
  } = $props();

  /** @type {Record<string, any> | null} */
  let ragStatus = $state(null);
  let ragStatusLoading = $state(false);
  let ragStatusError = $state("");
  /** @type {Record<string, any> | null} */
  let vectorStatus = $state(null);
  let vectorStatusLoading = $state(false);
  let vectorStatusError = $state("");
  let rebuildingRagIndex = $state(false);
  let rebuildingVectorIndex = $state(false);
  let ragRebuildMessage = $state("");
  let vectorRebuildMessage = $state("");

  /** @type {Record<string, Array<Record<string, any>>>} */
  let memoryGroups = $state({});
  let memoryLoading = $state(false);
  let memoryError = $state("");
  let deletingMemoryId = $state("");
  let memoryMessage = $state("");
  let updatingMemoryId = $state("");
  let memoryFilterKind = $state("all");
  let memoryFilterStatus = $state("all");
  let memoryFilterSource = $state("all");
  let memoryFilterRag = $state("all");
  let memoryFilterCharacter = $state("");
  let memoryFilterLocation = $state("");
  let memoryFilterTopic = $state("");
  /** @type {Array<Record<string, any>>} */
  let consolidationSuggestions = $state([]);
  let consolidationLoading = $state(false);
  let consolidationRunning = $state(false);
  let consolidationError = $state("");
  let consolidationMessage = $state("");
  let updatingSuggestionId = $state("");

  const memoryFilterOptions = $derived(buildMemoryFilterOptions(memoryGroups));
  const consolidationProfileOptions = $derived(profiles.filter((profile) => profile.kind === "memory_summary" || profile.kind === "state_update" || profile.kind === "roleplay"));

  export async function loadRagStatus() {
    if (!scenarioId) return;
    ragStatusLoading = true;
    ragStatusError = "";
    vectorStatusLoading = true;
    vectorStatusError = "";
    ragRebuildMessage = "";
    vectorRebuildMessage = "";
    try {
      ragStatus = await getScenarioRagStatus(scenarioId);
    } catch (caught) {
      ragStatusError = caught instanceof Error ? caught.message : translateNow("editor.ragStatusError");
    } finally {
      ragStatusLoading = false;
    }
    try {
      vectorStatus = await getScenarioRagVectorStatus(scenarioId);
    } catch (caught) {
      vectorStatusError = caught instanceof Error ? caught.message : translateNow("editor.vectorStatusError");
    } finally {
      vectorStatusLoading = false;
    }
  }

  async function doRebuildRagIndex() {
    if (!scenarioId || rebuildingRagIndex) return;
    rebuildingRagIndex = true;
    ragRebuildMessage = "";
    try {
      const result = await rebuildScenarioRagIndex(scenarioId);
      ragRebuildMessage = translateNow("editor.rebuildDone", { count: result.index?.document_count ?? 0 });
      ragStatus = await getScenarioRagStatus(scenarioId);
    } catch (caught) {
      ragRebuildMessage = caught instanceof Error ? caught.message : translateNow("editor.rebuildError");
    } finally {
      rebuildingRagIndex = false;
    }
  }

  async function doRebuildVectorIndex() {
    if (!scenarioId || rebuildingVectorIndex) return;
    rebuildingVectorIndex = true;
    vectorRebuildMessage = "";
    try {
      const result = await rebuildScenarioVectorIndex(scenarioId);
      vectorRebuildMessage = translateNow("editor.vectorRebuildDone", { count: result.index?.document_count ?? 0, model: result.index?.model ?? "" });
      vectorStatus = await getScenarioRagVectorStatus(scenarioId);
    } catch (caught) {
      vectorRebuildMessage = caught instanceof Error ? caught.message : translateNow("editor.vectorRebuildError");
    } finally {
      rebuildingVectorIndex = false;
    }
  }

  export async function loadMemory() {
    if (!scenarioId) return;
    memoryLoading = true;
    memoryError = "";
    memoryMessage = "";
    try {
      const payload = await listScenarioMemory(scenarioId);
      memoryGroups = payload.groups || {};
    } catch (caught) {
      memoryError = caught instanceof Error ? caught.message : translateNow("editor.loadFilesError");
    } finally {
      memoryLoading = false;
    }
  }

  export async function loadConsolidationSuggestions() {
    if (!scenarioId) return;
    consolidationLoading = true;
    consolidationError = "";
    try {
      const payload = await listMemoryConsolidationSuggestions(scenarioId);
      consolidationSuggestions = payload.suggestions || [];
    } catch (caught) {
      consolidationError = caught instanceof Error ? caught.message : translateNow("editor.consolidationLoadError");
    } finally {
      consolidationLoading = false;
    }
  }

  async function doCreateConsolidationSuggestions() {
    if (!scenarioId || consolidationRunning || !consolidationSessionId || !consolidationProfileId) return;
    consolidationRunning = true;
    consolidationError = "";
    consolidationMessage = "";
    try {
      const payload = await createMemoryConsolidationSuggestions(scenarioId, {
        session_id: consolidationSessionId,
        profile_id: consolidationProfileId
      });
      consolidationMessage = translateNow("editor.consolidationCreated", { count: payload.created_files?.length ?? 0 });
      await loadConsolidationSuggestions();
    } catch (caught) {
      consolidationError = caught instanceof Error ? caught.message : translateNow("editor.consolidationCreateError");
    } finally {
      consolidationRunning = false;
    }
  }

  /**
   * @param {string} suggestionId
   * @param {string} status
   */
  async function doSetSuggestionStatus(suggestionId, status) {
    if (!scenarioId || updatingSuggestionId) return;
    updatingSuggestionId = suggestionId;
    consolidationError = "";
    consolidationMessage = "";
    try {
      await updateMemoryConsolidationSuggestionStatus(scenarioId, suggestionId, status);
      consolidationMessage = translateNow("editor.consolidationStatusSaved");
      await loadConsolidationSuggestions();
    } catch (caught) {
      consolidationError = caught instanceof Error ? caught.message : translateNow("editor.consolidationUpdateError");
    } finally {
      updatingSuggestionId = "";
    }
  }

  /** @param {string} suggestionId */
  async function doApplySuggestion(suggestionId) {
    if (!scenarioId || updatingSuggestionId) return;
    updatingSuggestionId = suggestionId;
    consolidationError = "";
    consolidationMessage = "";
    try {
      const payload = await applyMemoryConsolidationSuggestion(scenarioId, suggestionId);
      consolidationMessage = translateNow("editor.consolidationApplied", { count: payload.updated_memory_paths?.length ?? 0 });
      await Promise.all([loadConsolidationSuggestions(), loadMemory()]);
    } catch (caught) {
      consolidationError = caught instanceof Error ? caught.message : translateNow("editor.consolidationUpdateError");
    } finally {
      updatingSuggestionId = "";
    }
  }

  /**
   * @param {string} kind
   * @param {Record<string, any>} item
   */
  function memoryMatchesFilters(kind, item) {
    return memoryItemMatchesFilters(kind, item, {
      kind: memoryFilterKind,
      status: memoryFilterStatus,
      source: memoryFilterSource,
      rag: memoryFilterRag,
      character: memoryFilterCharacter,
      location: memoryFilterLocation,
      topic: memoryFilterTopic
    });
  }

  /**
   * @param {string} kind
   * @param {string} memoryId
   * @param {boolean} ragEnabled
   */
  async function doSetMemoryRag(kind, memoryId, ragEnabled) {
    if (!scenarioId || updatingMemoryId) return;
    updatingMemoryId = `${kind}/${memoryId}`;
    memoryMessage = "";
    memoryError = "";
    try {
      await updateMemoryMetadata(scenarioId, kind, memoryId, { rag_enabled: ragEnabled });
      memoryMessage = ragEnabled ? translateNow("editor.memoryRagEnabled") : translateNow("editor.memoryRagDisabled");
      await loadMemory();
    } catch (caught) {
      memoryError = caught instanceof Error ? caught.message : translateNow("editor.memoryUpdateError");
    } finally {
      updatingMemoryId = "";
    }
  }

  /**
   * @param {string} kind
   * @param {string} memoryId
   */
  async function doResolveMemory(kind, memoryId) {
    if (!scenarioId || updatingMemoryId) return;
    updatingMemoryId = `${kind}/${memoryId}`;
    memoryMessage = "";
    memoryError = "";
    try {
      await updateMemoryMetadata(scenarioId, kind, memoryId, { status: "resolved" });
      memoryMessage = translateNow("editor.memoryResolved");
      await loadMemory();
    } catch (caught) {
      memoryError = caught instanceof Error ? caught.message : translateNow("editor.memoryUpdateError");
    } finally {
      updatingMemoryId = "";
    }
  }

  /** @param {string} path */
  async function openMemorySource(path) {
    if (!path) return;
    await openSource(path);
  }

  /**
   * @param {string} kind
   * @param {string} memoryId
   */
  async function doDeleteMemory(kind, memoryId) {
    if (!scenarioId || deletingMemoryId) return;
    if (!window.confirm(translateNow("editor.memoryDeleteConfirm", { id: memoryId }))) return;
    deletingMemoryId = `${kind}/${memoryId}`;
    memoryMessage = "";
    try {
      await deleteMemory(scenarioId, kind, memoryId);
      memoryMessage = translateNow("editor.memoryDeleted", { id: memoryId });
      await loadMemory();
    } catch (caught) {
      memoryError = caught instanceof Error ? caught.message : translateNow("editor.memoryDeleteError");
    } finally {
      deletingMemoryId = "";
    }
  }
</script>

<div class="rag-status-panel" style:display={hidden ? "none" : null}>
  <div class="knowledge-divider"><span>RAG</span></div>
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

  <div class="knowledge-divider"><span>{$t("editor.memoryList")}</span></div>

  {#if memoryMessage}
    <p class="rag-message">{memoryMessage}</p>
  {/if}
  {#if memoryError}
    <p class="notice error-notice">{memoryError}</p>
  {/if}
  <div class="memory-filter-grid">
    <label>
      <span>{$t("editor.memoryFilterKind")}</span>
      <select bind:value={memoryFilterKind}>
        <option value="all">{$t("common.all")}</option>
        {#each memoryFilterOptions.kinds as kind}
          <option value={kind}>{kind}</option>
        {/each}
      </select>
    </label>
    <label>
      <span>{$t("editor.memoryFilterStatus")}</span>
      <select bind:value={memoryFilterStatus}>
        <option value="all">{$t("common.all")}</option>
        {#each memoryFilterOptions.statuses as status}
          <option value={status}>{status}</option>
        {/each}
      </select>
    </label>
    <label>
      <span>{$t("editor.memoryFilterSource")}</span>
      <select bind:value={memoryFilterSource}>
        <option value="all">{$t("common.all")}</option>
        {#each memoryFilterOptions.sources as source}
          <option value={source}>{source}</option>
        {/each}
      </select>
    </label>
    <label>
      <span>{$t("editor.memoryFilterRag")}</span>
      <select bind:value={memoryFilterRag}>
        <option value="all">{$t("common.all")}</option>
        <option value="enabled">{$t("editor.memoryRagEnabledShort")}</option>
        <option value="disabled">{$t("editor.memoryRagDisabledShort")}</option>
      </select>
    </label>
    <label>
      <span>{$t("editor.memoryFilterCharacters")}</span>
      <input bind:value={memoryFilterCharacter} type="search" />
    </label>
    <label>
      <span>{$t("editor.memoryFilterLocations")}</span>
      <input bind:value={memoryFilterLocation} type="search" />
    </label>
    <label>
      <span>{$t("editor.memoryFilterTopics")}</span>
      <input bind:value={memoryFilterTopic} type="search" />
    </label>
  </div>
  {#if memoryLoading}
    <p class="notice">{$t("editor.loadingFiles")}</p>
  {:else}
    {#each Object.entries(memoryGroups) as [kind, items]}
      {@const filteredItems = items.filter((item) => memoryMatchesFilters(kind, item))}
      <div class="rag-section">
        <div class="rag-section-header">
          <h4>{kind}</h4>
          <span class="rag-count">{filteredItems.length}/{items.length}</span>
        </div>
        {#if filteredItems.length}
          <ul class="memory-list">
            {#each filteredItems as item}
              {@const memId = item.path.split("/").pop()?.replace(/\.md$/, "") ?? ""}
              <li class="memory-item">
                <div class="memory-item-info">
                  <span class="memory-item-title">{item.title || memId}</span>
                  <span class="memory-item-meta">
                    <span>{item.memory_kind || kind}</span>
                    <span>{item.status || "active"}</span>
                    <span>{item.source || "unknown"}</span>
                    <span>{item.rag_enabled ? $t("editor.memoryRagEnabledShort") : $t("editor.memoryRagDisabledShort")}</span>
                  </span>
                  {#if item.excerpt}
                    <span class="memory-item-excerpt">{item.excerpt}</span>
                  {/if}
                  <label class="memory-rag-toggle">
                    <input
                      type="checkbox"
                      checked={item.rag_enabled}
                      disabled={!!updatingMemoryId}
                      onchange={(event) => void doSetMemoryRag(kind, memId, event.currentTarget.checked)}
                    />
                    <span>{$t("editor.memoryRagToggle")}</span>
                  </label>
                </div>
                <div class="memory-item-actions">
                  <button
                    class="icon-button compact-icon"
                    type="button"
                    title={$t("editor.memoryOpenSource")}
                    onclick={() => void openMemorySource(item.path)}
                  >
                    <FilePenLine size={14} aria-hidden="true" />
                  </button>
                  <button
                    class="icon-button compact-icon"
                    type="button"
                    title={$t("editor.memoryMarkResolved")}
                    disabled={!!updatingMemoryId || item.status === "resolved"}
                    onclick={() => void doResolveMemory(kind, memId)}
                  >
                    <CircleCheck size={14} aria-hidden="true" />
                  </button>
                  <button
                    class="icon-button compact-icon"
                    type="button"
                    title={$t("common.delete")}
                    disabled={!!deletingMemoryId || !!updatingMemoryId}
                    onclick={() => void doDeleteMemory(kind, memId)}
                  >
                    <Trash2 size={14} aria-hidden="true" />
                  </button>
                </div>
              </li>
            {/each}
          </ul>
        {:else}
          <p class="notice">{$t("editor.noFiles")}</p>
        {/if}
      </div>
    {/each}
    {#if !Object.keys(memoryGroups).length}
      <p class="notice">{$t("editor.noFiles")}</p>
    {/if}
  {/if}

  <div class="knowledge-divider"><span>{$t("editor.consolidationSuggestions")}</span></div>
  <div class="rag-section">
    <div class="rag-section-header">
      <h4>{$t("editor.consolidationSuggestions")}</h4>
      <div class="rag-actions">
        <button class="icon-button compact-icon" type="button" title={$t("editor.reload")} onclick={() => void loadConsolidationSuggestions()}>
          <RotateCcw size={14} aria-hidden="true" />
        </button>
      </div>
    </div>
    <div class="consolidation-controls">
      <label>
        <span>{$t("editor.consolidationSession")}</span>
        <select bind:value={consolidationSessionId}>
          {#each sessions as session}
            <option value={session.session_id}>{session.display_name || session.session_id}</option>
          {/each}
        </select>
      </label>
      <label>
        <span>{$t("editor.consolidationProfile")}</span>
        <select bind:value={consolidationProfileId}>
          {#each consolidationProfileOptions as profile}
            <option value={profile.id}>{profile.id}</option>
          {/each}
        </select>
      </label>
      <button
        class="primary-button"
        type="button"
        disabled={consolidationRunning || !consolidationSessionId || !consolidationProfileId}
        onclick={() => void doCreateConsolidationSuggestions()}
      >
        {$t("editor.consolidationRun")}
      </button>
    </div>
    {#if consolidationMessage}
      <p class="rag-message">{consolidationMessage}</p>
    {/if}
    {#if consolidationError}
      <p class="notice error-notice">{consolidationError}</p>
    {/if}
    {#if consolidationLoading}
      <p class="notice">{$t("editor.loadingFiles")}</p>
    {:else if consolidationSuggestions.length}
      <ul class="memory-list">
        {#each consolidationSuggestions as suggestion}
          <li class="memory-item">
            <div class="memory-item-info">
              <span class="memory-item-title">{suggestion.title || suggestion.id}</span>
              <span class="memory-item-meta">
                <span>{suggestion.status}</span>
                <span>{suggestion.source}</span>
                <span>{suggestion.affected_memory_paths?.length ?? 0} paths</span>
              </span>
              {#if suggestion.content}
                <span class="memory-item-excerpt">{suggestion.content}</span>
              {/if}
              {#if suggestion.suggested_actions?.length}
                <ul class="suggested-action-list">
                  {#each suggestion.suggested_actions as action}
                    <li>
                      <code>{action.action}</code>
                      <span>{action.path}</span>
                      {#if action.status}
                        <span>{action.status}</span>
                      {/if}
                      {#if action.supersedes?.length}
                        <span>{action.supersedes.join(", ")}</span>
                      {/if}
                      {#if action.superseded_by?.length}
                        <span>{action.superseded_by.join(", ")}</span>
                      {/if}
                    </li>
                  {/each}
                </ul>
              {/if}
            </div>
            <button
              class="icon-button compact-icon"
              type="button"
              title={$t("editor.consolidationAccept")}
              disabled={!!updatingSuggestionId || suggestion.status === "accepted" || suggestion.status === "applied"}
              onclick={() => void doSetSuggestionStatus(suggestion.id, "accepted")}
            >
              <Save size={14} aria-hidden="true" />
            </button>
            <button
              class="icon-button compact-icon"
              type="button"
              title={$t("editor.consolidationReject")}
              disabled={!!updatingSuggestionId || suggestion.status === "rejected" || suggestion.status === "applied"}
              onclick={() => void doSetSuggestionStatus(suggestion.id, "rejected")}
            >
              <X size={14} aria-hidden="true" />
            </button>
            <button
              class="icon-button compact-icon"
              type="button"
              title={$t("editor.consolidationApply")}
              disabled={!!updatingSuggestionId || suggestion.status !== "accepted"}
              onclick={() => void doApplySuggestion(suggestion.id)}
            >
              <FilePenLine size={14} aria-hidden="true" />
            </button>
          </li>
        {/each}
      </ul>
    {:else}
      <p class="notice">{$t("editor.consolidationNoSuggestions")}</p>
    {/if}
  </div>
</div>

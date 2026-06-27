<script>
  import { RefreshCcw } from "lucide-svelte";
  import { renderMarkdown } from "./markdown.js";
  import { t, translateNow } from "./i18n.js";
  import {
    formatHeadingPath,
    formatMatchedTerms,
    groupedRagSources,
    isRagSourceContentTruncated,
    ragSourceContent,
    ragSourceContentLength,
    ragSourceContentPreview,
    ragSourceKey
  } from "./ragSources.js";

  /** @type {{
   *   scenarioId?: string,
   *   sessionId?: string,
   *   sessionNoteDraft?: string,
   *   sceneNoteDraft?: string,
   *   settingsSaving?: boolean,
   *   settingsMessage?: string,
   *   saveSessionSettings?: () => void,
   *   pinsLoading?: boolean,
   *   pinsSaving?: boolean,
   *   pinsMessage?: string,
   *   pinsData?: Record<string, any> | null,
   *   toggleMod?: (path: string) => void,
   *   togglePinnedCharacter?: (path: string) => void,
   *   promptPreviewLoading?: boolean,
   *   promptPreviewError?: string,
   *   promptPreview?: Record<string, any> | null,
   *   openRagSource?: (path: string) => void,
   *   ragStatusLoading?: boolean,
   *   ragStatusError?: string,
   *   ragStatus?: Record<string, any> | null,
   *   ragRebuildRunning?: boolean,
   *   ragRebuildMessage?: string,
   *   rebuildRagIndex?: () => void,
   *   memoryLoading?: boolean,
   *   memoryError?: string,
   *   memoryList?: Record<string, any> | null,
   *   memoryStatusSaving?: boolean,
   *   memoryStatusMessage?: string,
   *   activeMemoryPath?: string,
   *   selectedMemoryItem?: Record<string, any> | null,
   *   loadMemoryList?: (scenarioId: string, sessionId: string) => void,
   *   updateMemoryStatus?: (item: Record<string, any>, status: string) => void,
   * }} */
  let {
    scenarioId = "",
    sessionId = "",
    sessionNoteDraft = $bindable(""),
    sceneNoteDraft = $bindable(""),
    settingsSaving = false,
    settingsMessage = "",
    saveSessionSettings = () => {},
    pinsLoading = false,
    pinsSaving = false,
    pinsMessage = "",
    pinsData = null,
    toggleMod = (_path) => {},
    togglePinnedCharacter = (_path) => {},
    promptPreviewLoading = false,
    promptPreviewError = "",
    promptPreview = null,
    openRagSource = (_path) => {},
    ragStatusLoading = false,
    ragStatusError = "",
    ragStatus = null,
    ragRebuildRunning = false,
    ragRebuildMessage = "",
    rebuildRagIndex = () => {},
    memoryLoading = false,
    memoryError = "",
    memoryList = null,
    memoryStatusSaving = false,
    memoryStatusMessage = "",
    activeMemoryPath = $bindable(""),
    selectedMemoryItem = null,
    loadMemoryList = (_scenarioId, _sessionId) => {},
    updateMemoryStatus = (_item, _status) => {}
  } = $props();

  const memoryStatusOptions = ["active", "resolved", "superseded", "stale", "archived"];
  const ragPreviewLength = 320;
  /** @type {Record<string, boolean>} */
  let expandedRagGroups = $state({});
  /** @type {Record<string, boolean>} */
  let expandedRagItems = $state({});
  const currentMemoryItem = $derived(resolveMemoryItem(memoryList, activeMemoryPath) || selectedMemoryItem);

  function requestPayloadJson() {
    return JSON.stringify(promptPreview?.prompt?.request_payload || {}, null, 2);
  }

  function messagesJson() {
    return JSON.stringify(promptPreview?.prompt?.messages || [], null, 2);
  }

  function metadataJson() {
    return JSON.stringify(promptMetadata(), null, 2);
  }

  function promptMetadata() {
    const prompt = promptPreview?.prompt;
    if (!prompt || typeof prompt !== "object") return {};
    const {
      request_payload: _requestPayload,
      messages: _messages,
      ...metadata
    } = prompt;
    return metadata;
  }

  function tokenUsage() {
    return promptPreview?.prompt?.token_usage || null;
  }

  function tokenUsageWarning() {
    const usage = tokenUsage();
    if (!usage || typeof usage.total_context_ratio !== "number") return "";
    const maxTokens = Number(promptPreview?.prompt?.profile?.max_tokens ?? usage.reserved_response_tokens);
    if (!Number.isFinite(usage.context_size) || usage.context_size <= 0) {
      return "Context size が未設定または不正です。Profile 設定を確認してください。";
    }
    if (Number.isFinite(maxTokens) && maxTokens > 0 && usage.remaining_context_tokens < maxTokens) {
      return `Context 残量 ${formatNumber(usage.remaining_context_tokens)} tokens が max_tokens ${formatNumber(maxTokens)} を下回っています。`;
    }
    if (usage.total_context_ratio >= 1) {
      return translateNow("settings.contextOverflow");
    }
    if (usage.total_context_ratio >= 0.9) {
      return translateNow("settings.contextNear90");
    }
    return "";
  }

  function ragDebug() {
    return promptPreview?.prompt?.rag_debug || [];
  }

  function requestPayloadMessageCount() {
    const messages = promptPreview?.prompt?.request_payload?.messages;
    return Array.isArray(messages) ? messages.length : 0;
  }

  function ragSourceGroups() {
    return groupedRagSources(promptPreview?.prompt?.rag_results);
  }

  function ragSourceTotal() {
    return ragSourceGroups().reduce((total, group) => total + group.items.length, 0);
  }

  /** @param {string} type */
  function isRagGroupExpanded(type) {
    if (expandedRagGroups[type] !== undefined) return expandedRagGroups[type];
    return type === "memory";
  }

  /** @param {string} type */
  function toggleRagGroup(type) {
    expandedRagGroups = { ...expandedRagGroups, [type]: !isRagGroupExpanded(type) };
  }

  /** @param {boolean} expanded */
  function setAllRagGroups(expanded) {
    expandedRagGroups = Object.fromEntries(ragSourceGroups().map((group) => [group.type, expanded]));
  }

  /** @param {string} key */
  function toggleRagItem(key) {
    expandedRagItems = { ...expandedRagItems, [key]: expandedRagItems[key] !== true };
  }

  /** @param {Record<string, any>} budgets */
  function budgetSummary(budgets) {
    if (!budgets || typeof budgets !== "object") return "";
    return Object.entries(budgets).map(([key, value]) => `${key}: ${value}`).join(", ");
  }

  function memoryCounts() {
    return ragStatus?.memory?.counts || {};
  }

  function memoryTotal() {
    return typeof ragStatus?.memory?.total === "number" ? ragStatus.memory.total : 0;
  }

  function memoryGroups() {
    return memoryList?.groups || {};
  }

  /**
   * @param {Record<string, any> | null} list
   * @param {string} path
   */
  function resolveMemoryItem(list, path) {
    const groups = list?.groups || {};
    let first = null;
    for (const kind of ["session_summaries", "extracted_facts", "unresolved_threads"]) {
      const items = groups[kind];
      if (!Array.isArray(items)) continue;
      if (!first && items.length) first = items[0];
      const found = items.find((item) => item.path === path);
      if (found) return found;
    }
    return first;
  }

  /** @param {string} kind */
  function memoryKindLabel(kind) {
    return {
      session_summaries: "Session summaries",
      extracted_facts: "Facts",
      unresolved_threads: "Threads"
    }[kind] || kind;
  }

  /**
   * @param {number | null | undefined} value
   */
  function formatNumber(value) {
    return typeof value === "number" && Number.isFinite(value) ? value.toLocaleString() : translateNow("common.unrecorded");
  }

  /**
   * @param {number | null | undefined} value
   */
  function formatRatio(value) {
    if (typeof value !== "number" || !Number.isFinite(value)) {
      return translateNow("common.unrecorded");
    }
    return `${Math.round(value * 1000) / 10}%`;
  }
</script>

<div class="modal-grid">
  <section class="modal-section">
    <h4>Session Note</h4>
    <textarea
      class="settings-textarea"
      bind:value={sessionNoteDraft}
      placeholder={$t("settings.sessionNotePlaceholder")}
      rows="6"
    ></textarea>
    <h4>Scene Note</h4>
    <textarea
      class="settings-textarea"
      bind:value={sceneNoteDraft}
      placeholder={$t("settings.sceneNotePlaceholder")}
      rows="4"
    ></textarea>
    <div class="modal-actions">
      <button type="button" disabled={settingsSaving} onclick={() => void saveSessionSettings()}>
        {settingsSaving ? $t("settings.saving") : $t("settings.saveSettings")}
      </button>
      {#if settingsMessage}
        <span class="settings-message">{settingsMessage}</span>
      {/if}
    </div>
  </section>

  <section class="modal-section">
    <h4>Active Mods</h4>
    <p class="placeholder-copy">
      {@html $t("settings.modsDesc")}
    </p>
    {#if pinsLoading}
      <p class="placeholder-copy">{$t("settings.pinsLoading")}</p>
    {:else if !pinsData}
      <p class="placeholder-copy">{$t("settings.modsLoadError")}</p>
    {:else if pinsData.available_mods?.length === 0}
      <p class="placeholder-copy">{$t("settings.noMods")}</p>
    {:else}
      <ul class="pin-list">
        {#each pinsData.available_mods as mod}
          {@const active = Array.isArray(pinsData.active_mods) && pinsData.active_mods.includes(mod.path)}
          <li class="pin-item">
            <label class="pin-label">
              <input
                type="checkbox"
                checked={active}
                disabled={pinsSaving}
                onchange={() => void toggleMod(mod.path)}
              />
              <span class="pin-title">{mod.title}</span>
              <span class="pin-path">{mod.path}</span>
            </label>
          </li>
        {/each}
      </ul>
    {/if}
    {#if pinsData?.warnings?.filter((/** @type {string} */ w) => w.startsWith("lore/")).length}
      <ul class="pin-warnings">
        {#each pinsData.warnings.filter((/** @type {string} */ w) => w.startsWith("lore/")) as w}
          <li class="pin-warning">⚠ {w}</li>
        {/each}
      </ul>
    {/if}
    {#if pinsMessage}
      <span class="settings-message">{pinsMessage}</span>
    {/if}
  </section>

  <section class="modal-section">
    <h4>Pinned Characters</h4>
    <p class="placeholder-copy">
      {$t("settings.pinnedCharsDesc")}
    </p>
    {#if pinsLoading}
      <p class="placeholder-copy">{$t("settings.pinsLoading")}</p>
    {:else if !pinsData}
      <p class="placeholder-copy">{$t("settings.charsLoadError")}</p>
    {:else if pinsData.available_characters?.length === 0}
      <p class="placeholder-copy">{$t("settings.noChars")}</p>
    {:else}
      <ul class="pin-list">
        {#each pinsData.available_characters ?? [] as char}
          {@const pinned = Array.isArray(pinsData.pinned_characters) && pinsData.pinned_characters.includes(char.path)}
          <li class="pin-item">
            <label class="pin-label">
              <input
                type="checkbox"
                checked={pinned}
                disabled={pinsSaving}
                onchange={() => void togglePinnedCharacter(char.path)}
              />
              <span class="pin-title">{char.title}</span>
              <span class="pin-path">{char.path}</span>
            </label>
          </li>
        {/each}
      </ul>
    {/if}
    {#if pinsData?.warnings?.filter((/** @type {string} */ w) => w.startsWith("characters/")).length}
      <ul class="pin-warnings">
        {#each pinsData.warnings.filter((/** @type {string} */ w) => w.startsWith("characters/")) as w}
          <li class="pin-warning">⚠ {w}</li>
        {/each}
      </ul>
    {/if}
  </section>

  <section class="modal-section">
    <h4>Token Usage</h4>
    <p class="placeholder-copy">
      {$t("settings.tokenUsageDesc")}
    </p>
    {#if promptPreviewLoading}
      <p class="placeholder-copy">{$t("settings.tokenUsageLoading")}</p>
    {:else if promptPreviewError}
      <p class="placeholder-copy error-copy">{promptPreviewError}</p>
    {:else if tokenUsage()}
      {#if tokenUsageWarning()}
        <p class="placeholder-copy error-copy">{tokenUsageWarning()}</p>
      {/if}
      <dl class="info-list compact-list">
        <div><dt>Mode</dt><dd>{tokenUsage().estimate ? $t("settings.estimate") : $t("settings.actual")}</dd></div>
        <div><dt>Tokenizer</dt><dd>{tokenUsage().tokenizer || $t("common.unrecorded")}</dd></div>
        <div><dt>Prompt</dt><dd>{formatNumber(tokenUsage().prompt_tokens)}</dd></div>
        <div><dt>Reserved</dt><dd>{formatNumber(tokenUsage().reserved_response_tokens)}</dd></div>
        <div><dt>Total</dt><dd>{formatNumber(tokenUsage().total_with_reserved_response)}</dd></div>
        <div><dt>Context</dt><dd>{formatNumber(tokenUsage().context_size)}</dd></div>
        <div><dt>Remaining</dt><dd>{formatNumber(tokenUsage().remaining_context_tokens)}</dd></div>
        <div><dt>Usage</dt><dd>{formatRatio(tokenUsage().total_context_ratio)}</dd></div>
      </dl>
    {:else}
      <p class="placeholder-copy">
        {promptPreview?.has_prompt
          ? $t("settings.noTokenUsage")
          : promptPreview?.message || $t("settings.noPromptYet")}
      </p>
    {/if}
  </section>

  <section class="modal-section">
    <h4>{$t("settings.latestPromptHeading")}</h4>
    <p class="placeholder-copy">
      {$t("settings.latestPromptDesc")}
    </p>
    {#if promptPreviewLoading}
      <p class="placeholder-copy">{$t("settings.latestPromptLoading")}</p>
    {:else if promptPreviewError}
      <p class="placeholder-copy error-copy">{promptPreviewError}</p>
    {:else if promptPreview?.has_prompt}
      <dl class="info-list compact-list">
        <div><dt>Turn</dt><dd>{promptPreview.prompt?.turn ?? $t("common.unrecorded")}</dd></div>
        <div><dt>Profile</dt><dd>{promptPreview.prompt?.profile?.id || $t("common.unrecorded")}</dd></div>
        <div><dt>Model</dt><dd>{promptPreview.prompt?.profile?.model || $t("common.unrecorded")}</dd></div>
        <div><dt>Request messages</dt><dd>{requestPayloadMessageCount()}</dd></div>
        <div><dt>Saved messages</dt><dd>{promptPreview.prompt?.message_count ?? 0}</dd></div>
        <div><dt>Characters</dt><dd>{promptPreview.prompt?.character_count ?? 0}</dd></div>
        <div><dt>Saved</dt><dd>{promptPreview.prompt?.saved_at || $t("common.unrecorded")}</dd></div>
      </dl>
      <div class="latest-prompt-parts">
        <section class="latest-prompt-part" aria-labelledby="latest-request-payload-heading">
          <div>
            <h5 id="latest-request-payload-heading">{$t("settings.latestPromptRequestPayload")}</h5>
            <p class="placeholder-copy">{$t("settings.latestPromptRequestPayloadDesc")}</p>
          </div>
          <pre class="prompt-preview-block">{requestPayloadJson()}</pre>
        </section>
        <section class="latest-prompt-part" aria-labelledby="latest-messages-heading">
          <div>
            <h5 id="latest-messages-heading">{$t("settings.latestPromptMessages")}</h5>
            <p class="placeholder-copy">{$t("settings.latestPromptMessagesDesc")}</p>
          </div>
          <pre class="prompt-preview-block">{messagesJson()}</pre>
        </section>
        <section class="latest-prompt-part" aria-labelledby="latest-metadata-heading">
          <div>
            <h5 id="latest-metadata-heading">{$t("settings.latestPromptMetadata")}</h5>
            <p class="placeholder-copy">{$t("settings.latestPromptMetadataDesc")}</p>
          </div>
          <pre class="prompt-preview-block">{metadataJson()}</pre>
        </section>
      </div>
    {:else}
      <p class="placeholder-copy">
        {promptPreview?.message || $t("settings.noPromptYet2")}
      </p>
    {/if}
  </section>

  <section class="modal-section">
    <h4>RAG Context</h4>
    <p class="placeholder-copy">
      {$t("settings.ragContextDesc")}
    </p>
    {#if promptPreviewLoading}
      <p class="placeholder-copy">{$t("settings.ragContextLoading")}</p>
    {:else if promptPreviewError}
      <p class="placeholder-copy error-copy">{promptPreviewError}</p>
    {:else if promptPreview?.prompt?.rag_results?.length}
      <div class="rag-current-summary">
        <strong>今回参照された Memory / Lore</strong>
        <span>{ragSourceTotal()} sources</span>
        <div class="rag-current-chips">
          {#each ragSourceGroups() as group}
            <span>{group.label}: {group.items.length}</span>
          {/each}
        </div>
      </div>
      {#if ragDebug().length}
        <dl class="info-list compact-list">
          {#each ragDebug() as debug}
            <div class="rag-query-row">
              <dt>Query</dt>
              <dd>
                <textarea class="rag-query-textarea" readonly rows="4" value={debug.query || $t("common.unrecorded")}></textarea>
              </dd>
            </div>
            <div><dt>Sources</dt><dd>{debug.sources?.join(", ") || $t("common.unrecorded")}</dd></div>
            <div><dt>Budget</dt><dd>total {debug.token_budget ?? $t("common.unrecorded")} / keyword {debug.keyword_token_budget ?? $t("common.unrecorded")} / {budgetSummary(debug.token_budgets)}</dd></div>
            <div><dt>Retrieved</dt><dd>{debug.retrieved_count ?? 0} / included {debug.included_count ?? 0}</dd></div>
            <div><dt>Skipped</dt><dd>{debug.skipped_reason || $t("common.none")}</dd></div>
          {/each}
        </dl>
      {/if}
      <div class="rag-source-groups">
        <div class="rag-context-actions">
          <button type="button" onclick={() => setAllRagGroups(true)}>{$t("settings.ragExpandAll")}</button>
          <button type="button" onclick={() => setAllRagGroups(false)}>{$t("settings.ragCollapseAll")}</button>
        </div>
        {#each ragSourceGroups() as group}
          <section class="rag-source-group" aria-label={group.label}>
            <button
              class="rag-source-group-toggle"
              type="button"
              aria-expanded={isRagGroupExpanded(group.type)}
              onclick={() => toggleRagGroup(group.type)}
            >
              <span>{isRagGroupExpanded(group.type) ? "▾" : "▸"} {group.label}</span>
              <small>{group.items.length} sources</small>
            </button>
            {#if isRagGroupExpanded(group.type)}
              <div class="rag-result-list">
                {#each group.items as result, index}
                  {@const itemKey = ragSourceKey(result, index)}
                  {@const contentLength = ragSourceContentLength(result)}
                  {@const expanded = expandedRagItems[itemKey] === true}
                  <article class="rag-result-card">
                    <div class="rag-result-head">
                      <strong>{result.title || result.source_path}</strong>
                      <span>{result.type || "rag"} / score {result.score ?? $t("common.unrecorded")} / {formatNumber(contentLength)} chars</span>
                    </div>
                    <button
                      class="source-link-button"
                      type="button"
                      disabled={!result.source_path}
                      onclick={() => openRagSource(result.source_path)}
                    >
                      {result.source_path}
                    </button>
                    <dl class="info-list compact-list rag-source-meta">
                      {#if result.chunk_id}
                        <div><dt>Chunk</dt><dd>{result.chunk_id}</dd></div>
                      {/if}
                      {#if formatHeadingPath(result.heading_path)}
                        <div><dt>Heading</dt><dd>{formatHeadingPath(result.heading_path)}</dd></div>
                      {/if}
                      {#if formatMatchedTerms(result.matched_terms)}
                        <div><dt>Matched</dt><dd>{formatMatchedTerms(result.matched_terms)}</dd></div>
                      {/if}
                      {#if result.metadata?.status}
                        <div><dt>Status</dt><dd>{result.metadata.status}</dd></div>
                      {/if}
                      {#if result.metadata?.importance !== undefined && result.metadata?.importance !== null}
                        <div><dt>Importance</dt><dd>{result.metadata.importance}</dd></div>
                      {/if}
                      {#if result.metadata?.turn_range}
                        <div><dt>Turn range</dt><dd>{Array.isArray(result.metadata.turn_range) ? result.metadata.turn_range.join(" - ") : result.metadata.turn_range}</dd></div>
                      {/if}
                      {#if result.metadata?.session_id}
                        <div><dt>Session</dt><dd>{result.metadata.session_id}</dd></div>
                      {/if}
                    </dl>
                    {#if contentLength}
                      <pre class="rag-content-preview">{expanded ? ragSourceContent(result) : ragSourceContentPreview(result, ragPreviewLength)}</pre>
                      {#if isRagSourceContentTruncated(result, ragPreviewLength)}
                        <button class="text-button compact" type="button" onclick={() => toggleRagItem(itemKey)}>
                          {expanded ? $t("settings.ragShowPreview") : $t("settings.ragShowFull")}
                        </button>
                      {/if}
                    {:else}
                      <p>{$t("settings.noContent")}</p>
                    {/if}
                  </article>
                {/each}
              </div>
            {/if}
          </section>
        {/each}
      </div>
    {:else}
      {#if ragDebug().length}
        <dl class="info-list compact-list">
          {#each ragDebug() as debug}
            <div class="rag-query-row">
              <dt>Query</dt>
              <dd>
                <textarea class="rag-query-textarea" readonly rows="4" value={debug.query || $t("common.unrecorded")}></textarea>
              </dd>
            </div>
            <div><dt>Sources</dt><dd>{debug.sources?.join(", ") || $t("common.unrecorded")}</dd></div>
            <div><dt>Budget</dt><dd>total {debug.token_budget ?? $t("common.unrecorded")} / keyword {debug.keyword_token_budget ?? $t("common.unrecorded")} / {budgetSummary(debug.token_budgets)}</dd></div>
            <div><dt>Retrieved</dt><dd>{debug.retrieved_count ?? 0} / included {debug.included_count ?? 0}</dd></div>
            <div><dt>Skipped</dt><dd>{debug.skipped_reason || $t("common.none")}</dd></div>
          {/each}
        </dl>
      {/if}
      <p class="placeholder-copy">
        {promptPreview?.has_prompt
          ? $t("settings.ragNoResults")
          : $t("settings.ragNoPrompt")}
      </p>
    {/if}
  </section>

  <section class="modal-section">
    <h4>Memory / RAG Status</h4>
    <p class="placeholder-copy">
      {$t("settings.memoryRagDesc")}
    </p>
    {#if ragStatusLoading}
      <p class="placeholder-copy">{$t("settings.ragStatusLoading")}</p>
    {:else if ragStatusError}
      <p class="placeholder-copy error-copy">{ragStatusError}</p>
    {:else if ragStatus}
      {#if ragStatus.rag_index?.stale || ragStatus.rag_index?.rebuild_needed}
        <p class="placeholder-copy error-copy">RAG index の再構築が必要です。下のボタンから再構築できます。</p>
      {/if}
      <dl class="info-list compact-list">
        <div><dt>Memory files</dt><dd>{memoryTotal()}</dd></div>
        <div><dt>Session summaries</dt><dd>{memoryCounts().session_summaries ?? 0}</dd></div>
        <div><dt>Facts</dt><dd>{memoryCounts().extracted_facts ?? 0}</dd></div>
        <div><dt>Threads</dt><dd>{memoryCounts().unresolved_threads ?? 0}</dd></div>
        <div><dt>Index</dt><dd>{ragStatus.rag_index?.indexed ? "indexed" : $t("settings.notBuilt")}</dd></div>
        <div><dt>Documents</dt><dd>{ragStatus.rag_index?.document_count ?? 0}</dd></div>
        <div><dt>Indexed</dt><dd>{ragStatus.rag_index?.indexed_at || $t("common.unrecorded")}</dd></div>
        <div><dt>Rebuild</dt><dd>{ragStatus.rag_index?.rebuild_needed ? $t("settings.rebuildNeeded") : $t("settings.notNeeded")}</dd></div>
        <div><dt>Stale</dt><dd>{ragStatus.rag_index?.stale ? "rebuild needed" : $t("common.none")}</dd></div>
        <div><dt>Reason</dt><dd>{ragStatus.rag_index?.reason || $t("common.unrecorded")}</dd></div>
        <div><dt>Marked</dt><dd>{ragStatus.rag_index?.marked_at || $t("common.unrecorded")}</dd></div>
      </dl>
      <div class="modal-actions">
        <button type="button" disabled={ragRebuildRunning} onclick={() => void rebuildRagIndex()}>
          <RefreshCcw size={15} aria-hidden="true" />
          {ragRebuildRunning ? $t("settings.rebuilding") : $t("settings.rebuildIndex")}
        </button>
        {#if ragRebuildMessage}
          <span class="settings-message">{ragRebuildMessage}</span>
        {/if}
      </div>
      {#if ragStatus.rag_index?.created_files?.length}
        <div class="rag-result-list">
          {#each ragStatus.rag_index.created_files as sourcePath}
            <button
              class="source-link-button"
              type="button"
              onclick={() => openRagSource(sourcePath)}
            >
              {sourcePath}
            </button>
          {/each}
        </div>
      {/if}
      <div class="memory-browser">
        <div class="panel-header compact">
          <h5>Memory Markdown</h5>
          <button type="button" disabled={memoryLoading} onclick={() => scenarioId && sessionId && void loadMemoryList(scenarioId, sessionId)}>
            <RefreshCcw size={14} aria-hidden="true" />
            {memoryLoading ? $t("settings.memoryReloading") : $t("settings.memoryReload")}
          </button>
        </div>
        {#if memoryLoading}
          <p class="placeholder-copy">{$t("settings.memoryListLoading")}</p>
        {:else if memoryError}
          <p class="placeholder-copy error-copy">{memoryError}</p>
        {:else if memoryList?.total}
          <div class="memory-browser-grid">
            <div class="memory-kind-list">
              {#each ["session_summaries", "extracted_facts", "unresolved_threads"] as kind}
                {#if memoryGroups()[kind]?.length}
                  <section>
                    <h6>{memoryKindLabel(kind)} ({memoryGroups()[kind].length})</h6>
                    {#each memoryGroups()[kind] as item}
                      <article class="memory-kind-item" class:selected={currentMemoryItem?.path === item.path}>
                        <button
                          class="memory-kind-select-button"
                          type="button"
                          onclick={() => (activeMemoryPath = item.path)}
                        >
                          <strong>{item.title || item.path}</strong>
                          <span>{item.path}</span>
                          <small>
                            {item.status || "active"} / {item.rag_enabled ? $t("settings.ragEnabled") : $t("settings.ragDisabled")} / {item.in_index ? $t("settings.indexed") : $t("settings.notIndexed")}
                            {item.stale_created ? " / stale" : ""}
                          </small>
                        </button>
                      </article>
                    {/each}
                  </section>
                {/if}
              {/each}
            </div>
            {#if currentMemoryItem}
              <article class="memory-preview">
                <div class="rag-result-head">
                  <strong>{currentMemoryItem.title || currentMemoryItem.path}</strong>
                  <span>{currentMemoryItem.memory_kind || currentMemoryItem.kind}</span>
                </div>
                <button class="source-link-button" type="button" onclick={() => openRagSource(currentMemoryItem.path)}>
                  {currentMemoryItem.path}
                </button>
                <dl class="info-list compact-list">
                  <div>
                    <dt>Status</dt>
                    <dd>
                      <select
                        class="memory-status-select"
                        disabled={memoryStatusSaving}
                        value={currentMemoryItem.status || "active"}
                        onchange={(event) => void updateMemoryStatus(currentMemoryItem, event.currentTarget.value)}
                      >
                        {#each memoryStatusOptions as status}
                          <option value={status}>{status}</option>
                        {/each}
                      </select>
                    </dd>
                  </div>
                  <div><dt>RAG</dt><dd>{currentMemoryItem.rag_enabled ? $t("settings.ragEnabledShort") : $t("settings.ragDisabledShort")}</dd></div>
                  <div><dt>Index</dt><dd>{currentMemoryItem.in_index ? "indexed" : $t("settings.notIndexed")}</dd></div>
                  <div><dt>Stale</dt><dd>{currentMemoryItem.stale_created ? "created after index" : $t("common.none")}</dd></div>
                </dl>
                {#if memoryStatusMessage}
                  <p class="settings-message">{memoryStatusMessage}</p>
                {/if}
                <div class="memory-preview-body markdown-body">
                  {@html renderMarkdown(currentMemoryItem.content || $t("settings.noBody"))}
                </div>
              </article>
            {/if}
          </div>
        {:else}
          <p class="placeholder-copy">{$t("settings.noMemory")}</p>
        {/if}
      </div>
    {:else}
      <p class="placeholder-copy">{$t("settings.ragStatusNotLoaded")}</p>
    {/if}
  </section>
</div>

<script>
  import { RefreshCcw } from "lucide-svelte";
  import { renderMarkdown } from "./markdown.js";
  import { t, translateNow } from "./i18n.js";

  export let scenarioId = "";
  export let sessionNoteDraft = "";
  export let sceneNoteDraft = "";
  export let settingsSaving = false;
  export let settingsMessage = "";
  export let saveSessionSettings = () => {};
  export let pinsLoading = false;
  export let pinsSaving = false;
  export let pinsMessage = "";
  /** @type {Record<string, any> | null} */
  export let pinsData = null;
  export let toggleMod = (/** @type {string} */ _path) => {};
  export let togglePinnedCharacter = (/** @type {string} */ _path) => {};
  export let promptPreviewLoading = false;
  export let promptPreviewError = "";
  /** @type {Record<string, any> | null} */
  export let promptPreview = null;
  export let openRagSource = (/** @type {string} */ _path) => {};
  export let ragStatusLoading = false;
  export let ragStatusError = "";
  /** @type {Record<string, any> | null} */
  export let ragStatus = null;
  export let ragRebuildRunning = false;
  export let ragRebuildMessage = "";
  export let rebuildRagIndex = () => {};
  export let memoryLoading = false;
  export let memoryError = "";
  /** @type {Record<string, any> | null} */
  export let memoryList = null;
  export let activeMemoryPath = "";
  /** @type {Record<string, any> | null} */
  export let selectedMemoryItem = null;
  export let loadMemoryList = (/** @type {string} */ _scenarioId) => {};

  function promptJson() {
    return JSON.stringify(promptPreview?.prompt || {}, null, 2);
  }

  function tokenUsage() {
    return promptPreview?.prompt?.token_usage || null;
  }

  function tokenUsageWarning() {
    const usage = tokenUsage();
    if (!usage || typeof usage.total_context_ratio !== "number") return "";
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

  function memoryCounts() {
    return ragStatus?.memory?.counts || {};
  }

  function memoryTotal() {
    return typeof ragStatus?.memory?.total === "number" ? ragStatus.memory.total : 0;
  }

  function memoryGroups() {
    return memoryList?.groups || {};
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
        <div><dt>Messages</dt><dd>{promptPreview.prompt?.message_count ?? 0}</dd></div>
        <div><dt>Characters</dt><dd>{promptPreview.prompt?.character_count ?? 0}</dd></div>
        <div><dt>Saved</dt><dd>{promptPreview.prompt?.saved_at || $t("common.unrecorded")}</dd></div>
      </dl>
      <pre class="prompt-preview-block">{promptJson()}</pre>
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
      {#if ragDebug().length}
        <dl class="info-list compact-list">
          {#each ragDebug() as debug}
            <div><dt>Query</dt><dd>{debug.query || $t("common.unrecorded")}</dd></div>
            <div><dt>Sources</dt><dd>{debug.sources?.join(", ") || $t("common.unrecorded")}</dd></div>
            <div><dt>Retrieved</dt><dd>{debug.retrieved_count ?? 0} / included {debug.included_count ?? 0}</dd></div>
            <div><dt>Skipped</dt><dd>{debug.skipped_reason || $t("common.none")}</dd></div>
          {/each}
        </dl>
      {/if}
      <div class="rag-result-list">
        {#each promptPreview.prompt.rag_results as result}
          <article class="rag-result-card">
            <div class="rag-result-head">
              <strong>{result.title || result.source_path}</strong>
              <span>{result.type || "rag"} / score {result.score ?? $t("common.unrecorded")}</span>
            </div>
            <button
              class="source-link-button"
              type="button"
              disabled={!result.source_path}
              onclick={() => openRagSource(result.source_path)}
            >
              {result.source_path}
            </button>
            <p>{result.content || $t("settings.noContent")}</p>
          </article>
        {/each}
      </div>
    {:else}
      {#if ragDebug().length}
        <dl class="info-list compact-list">
          {#each ragDebug() as debug}
            <div><dt>Query</dt><dd>{debug.query || $t("common.unrecorded")}</dd></div>
            <div><dt>Sources</dt><dd>{debug.sources?.join(", ") || $t("common.unrecorded")}</dd></div>
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
          <button type="button" disabled={memoryLoading} onclick={() => scenarioId && void loadMemoryList(scenarioId)}>
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
                      <button
                        class:selected={selectedMemoryItem?.path === item.path}
                        type="button"
                        onclick={() => (activeMemoryPath = item.path)}
                      >
                        <strong>{item.title || item.path}</strong>
                        <span>{item.path}</span>
                        <small>
                          {item.rag_enabled ? $t("settings.ragEnabled") : $t("settings.ragDisabled")} / {item.in_index ? $t("settings.indexed") : $t("settings.notIndexed")}
                          {item.stale_created ? " / stale" : ""}
                        </small>
                      </button>
                    {/each}
                  </section>
                {/if}
              {/each}
            </div>
            {#if selectedMemoryItem}
              <article class="memory-preview">
                <div class="rag-result-head">
                  <strong>{selectedMemoryItem.title || selectedMemoryItem.path}</strong>
                  <span>{selectedMemoryItem.memory_kind || selectedMemoryItem.kind}</span>
                </div>
                <button class="source-link-button" type="button" onclick={() => openRagSource(selectedMemoryItem.path)}>
                  {selectedMemoryItem.path}
                </button>
                <dl class="info-list compact-list">
                  <div><dt>RAG</dt><dd>{selectedMemoryItem.rag_enabled ? $t("settings.ragEnabledShort") : $t("settings.ragDisabledShort")}</dd></div>
                  <div><dt>Index</dt><dd>{selectedMemoryItem.in_index ? "indexed" : $t("settings.notIndexed")}</dd></div>
                  <div><dt>Stale</dt><dd>{selectedMemoryItem.stale_created ? "created after index" : $t("common.none")}</dd></div>
                </dl>
                <div class="memory-preview-body markdown-body">
                  {@html renderMarkdown(selectedMemoryItem.content || $t("settings.noBody"))}
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

<script>
  import { RefreshCcw } from "lucide-svelte";
  import { renderMarkdown } from "./markdown.js";

  export let scenarioId = "";
  export let userNoteDraft = "";
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
    return typeof value === "number" && Number.isFinite(value) ? value.toLocaleString() : "未記録";
  }

  /**
   * @param {number | null | undefined} value
   */
  function formatRatio(value) {
    if (typeof value !== "number" || !Number.isFinite(value)) {
      return "未記録";
    }
    return `${Math.round(value * 1000) / 10}%`;
  }
</script>

<div class="modal-grid">
  <section class="modal-section">
    <h4>User Note</h4>
    <textarea
      class="settings-textarea"
      bind:value={userNoteDraft}
      placeholder="このセッションだけに効かせたい補足メモ"
      rows="6"
    ></textarea>
    <div class="modal-actions">
      <button type="button" disabled={settingsSaving} onclick={() => void saveSessionSettings()}>
        {settingsSaving ? "保存中" : "変更を保存"}
      </button>
      {#if settingsMessage}
        <span class="settings-message">{settingsMessage}</span>
      {/if}
    </div>
  </section>

  <section class="modal-section">
    <h4>Active Mods</h4>
    <p class="placeholder-copy">
      <code>mod: true</code> を持つ Lore ファイルを常時Promptへロードします。RAG検索対象外になります。
    </p>
    {#if pinsLoading}
      <p class="placeholder-copy">読み込んでいます…</p>
    {:else if !pinsData}
      <p class="placeholder-copy">Mods 情報を取得できませんでした。</p>
    {:else if pinsData.available_mods?.length === 0}
      <p class="placeholder-copy">mod: true を持つ Lore ファイルがありません。</p>
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
      常時 Prompt へフルロードするキャラクターを選択します。RAG検索対象外になります。
    </p>
    {#if pinsLoading}
      <p class="placeholder-copy">読み込んでいます…</p>
    {:else if !pinsData}
      <p class="placeholder-copy">Characters 情報を取得できませんでした。</p>
    {:else if pinsData.available_characters?.length === 0}
      <p class="placeholder-copy">キャラクターファイルがありません。</p>
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
      最後に実際送信されたPromptに紐づく概算です。Scenario Editor の事前Previewとは別の保存済みデータを参照します。
    </p>
    {#if promptPreviewLoading}
      <p class="placeholder-copy">Token Usage を読み込んでいます。</p>
    {:else if promptPreviewError}
      <p class="placeholder-copy error-copy">{promptPreviewError}</p>
    {:else if tokenUsage()}
      <dl class="info-list compact-list">
        <div><dt>Mode</dt><dd>{tokenUsage().estimate ? "概算" : "実測"}</dd></div>
        <div><dt>Tokenizer</dt><dd>{tokenUsage().tokenizer || "未記録"}</dd></div>
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
          ? "このPromptにはToken Usageがまだ保存されていません。次の会話後に表示されます。"
          : promptPreview?.message || "まだ送信済みプロンプトはありません。次の会話後にToken Usageを表示します。"}
      </p>
    {/if}
  </section>

  <section class="modal-section">
    <h4>最新送信Prompt</h4>
    <p class="placeholder-copy">
      このセッションで最後にGMモデルへ実際送信したPromptです。保存対象は最新1件のみです。
    </p>
    {#if promptPreviewLoading}
      <p class="placeholder-copy">最新送信Prompt を読み込んでいます。</p>
    {:else if promptPreviewError}
      <p class="placeholder-copy error-copy">{promptPreviewError}</p>
    {:else if promptPreview?.has_prompt}
      <dl class="info-list compact-list">
        <div><dt>Turn</dt><dd>{promptPreview.prompt?.turn ?? "未記録"}</dd></div>
        <div><dt>Profile</dt><dd>{promptPreview.prompt?.profile?.id || "未記録"}</dd></div>
        <div><dt>Model</dt><dd>{promptPreview.prompt?.profile?.model || "未記録"}</dd></div>
        <div><dt>Messages</dt><dd>{promptPreview.prompt?.message_count ?? 0}</dd></div>
        <div><dt>Characters</dt><dd>{promptPreview.prompt?.character_count ?? 0}</dd></div>
        <div><dt>Saved</dt><dd>{promptPreview.prompt?.saved_at || "未記録"}</dd></div>
      </dl>
      <pre class="prompt-preview-block">{promptJson()}</pre>
    {:else}
      <p class="placeholder-copy">
        {promptPreview?.message || "まだ送信済みプロンプトはありません。次の会話後にここへ表示されます。"}
      </p>
    {/if}
  </section>

  <section class="modal-section">
    <h4>RAG Context</h4>
    <p class="placeholder-copy">
      最新送信Promptへ実際に入った検索結果です。source path から該当Markdownへ移動できます。
    </p>
    {#if promptPreviewLoading}
      <p class="placeholder-copy">RAG Context を読み込んでいます。</p>
    {:else if promptPreviewError}
      <p class="placeholder-copy error-copy">{promptPreviewError}</p>
    {:else if promptPreview?.prompt?.rag_results?.length}
      {#if ragDebug().length}
        <dl class="info-list compact-list">
          {#each ragDebug() as debug}
            <div><dt>Query</dt><dd>{debug.query || "未記録"}</dd></div>
            <div><dt>Sources</dt><dd>{debug.sources?.join(", ") || "未記録"}</dd></div>
            <div><dt>Retrieved</dt><dd>{debug.retrieved_count ?? 0} / included {debug.included_count ?? 0}</dd></div>
            <div><dt>Skipped</dt><dd>{debug.skipped_reason || "なし"}</dd></div>
          {/each}
        </dl>
      {/if}
      <div class="rag-result-list">
        {#each promptPreview.prompt.rag_results as result}
          <article class="rag-result-card">
            <div class="rag-result-head">
              <strong>{result.title || result.source_path}</strong>
              <span>{result.type || "rag"} / score {result.score ?? "未記録"}</span>
            </div>
            <button
              class="source-link-button"
              type="button"
              disabled={!result.source_path}
              onclick={() => openRagSource(result.source_path)}
            >
              {result.source_path}
            </button>
            <p>{result.content || "本文抜粋なし"}</p>
          </article>
        {/each}
      </div>
    {:else}
      {#if ragDebug().length}
        <dl class="info-list compact-list">
          {#each ragDebug() as debug}
            <div><dt>Query</dt><dd>{debug.query || "未記録"}</dd></div>
            <div><dt>Sources</dt><dd>{debug.sources?.join(", ") || "未記録"}</dd></div>
            <div><dt>Retrieved</dt><dd>{debug.retrieved_count ?? 0} / included {debug.included_count ?? 0}</dd></div>
            <div><dt>Skipped</dt><dd>{debug.skipped_reason || "なし"}</dd></div>
          {/each}
        </dl>
      {/if}
      <p class="placeholder-copy">
        {promptPreview?.has_prompt
          ? "このPromptにはRAG検索結果が入りませんでした。"
          : "まだ送信済みPromptがないため、RAG検索結果もありません。"}
      </p>
    {/if}
  </section>

  <section class="modal-section">
    <h4>Memory / RAG Status</h4>
    <p class="placeholder-copy">
      自動生成memoryと、派生データであるRAG indexの状態です。Vault上のMarkdownが正本です。
    </p>
    {#if ragStatusLoading}
      <p class="placeholder-copy">RAG status を読み込んでいます。</p>
    {:else if ragStatusError}
      <p class="placeholder-copy error-copy">{ragStatusError}</p>
    {:else if ragStatus}
      <dl class="info-list compact-list">
        <div><dt>Memory files</dt><dd>{memoryTotal()}</dd></div>
        <div><dt>Session summaries</dt><dd>{memoryCounts().session_summaries ?? 0}</dd></div>
        <div><dt>Facts</dt><dd>{memoryCounts().extracted_facts ?? 0}</dd></div>
        <div><dt>Threads</dt><dd>{memoryCounts().unresolved_threads ?? 0}</dd></div>
        <div><dt>Index</dt><dd>{ragStatus.rag_index?.indexed ? "indexed" : "未構築"}</dd></div>
        <div><dt>Documents</dt><dd>{ragStatus.rag_index?.document_count ?? 0}</dd></div>
        <div><dt>Indexed</dt><dd>{ragStatus.rag_index?.indexed_at || "未記録"}</dd></div>
        <div><dt>Rebuild</dt><dd>{ragStatus.rag_index?.rebuild_needed ? "needed" : "不要"}</dd></div>
        <div><dt>Stale</dt><dd>{ragStatus.rag_index?.stale ? "rebuild needed" : "なし"}</dd></div>
        <div><dt>Reason</dt><dd>{ragStatus.rag_index?.reason || "未記録"}</dd></div>
        <div><dt>Marked</dt><dd>{ragStatus.rag_index?.marked_at || "未記録"}</dd></div>
      </dl>
      <div class="modal-actions">
        <button type="button" disabled={ragRebuildRunning} onclick={() => void rebuildRagIndex()}>
          <RefreshCcw size={15} aria-hidden="true" />
          {ragRebuildRunning ? "再構築中" : "Index再構築"}
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
            {memoryLoading ? "読込中" : "再読込"}
          </button>
        </div>
        {#if memoryLoading}
          <p class="placeholder-copy">Memory一覧を読み込んでいます。</p>
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
                          {item.rag_enabled ? "RAG対象" : "RAG除外"} / {item.in_index ? "index済み" : "未index"}
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
                  <div><dt>RAG</dt><dd>{selectedMemoryItem.rag_enabled ? "対象" : "除外"}</dd></div>
                  <div><dt>Index</dt><dd>{selectedMemoryItem.in_index ? "indexed" : "未index"}</dd></div>
                  <div><dt>Stale</dt><dd>{selectedMemoryItem.stale_created ? "created after index" : "なし"}</dd></div>
                </dl>
                <div class="memory-preview-body markdown-body">
                  {@html renderMarkdown(selectedMemoryItem.content || "本文なし")}
                </div>
              </article>
            {/if}
          </div>
        {:else}
          <p class="placeholder-copy">生成済み memory Markdown はまだありません。</p>
        {/if}
      </div>
    {:else}
      <p class="placeholder-copy">RAG status はまだ読み込まれていません。</p>
    {/if}
  </section>
</div>

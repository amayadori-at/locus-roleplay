<script>
  import { Maximize2, RotateCcw, Save, Tags, Trash2 } from "lucide-svelte";

  /** @type {{
   *   selectedPath?: string,
   *   loadingFile?: boolean,
   *   sourceDirty?: boolean,
   *   sourceMessage?: string,
   *   savingSource?: boolean,
   *   deletingSource?: boolean,
   *   sourceContent?: string,
   *   saveSourceFile?: () => void,
   *   resetSourceEdits?: () => void,
   *   deleteSourceFile?: () => void,
   *   canDeleteSelectedSource?: () => boolean,
   *   updateSourceDraft?: (event: Event) => void,
   *   expandSourceEditor?: () => void,
   *   applyFrontmatterFields?: (fields: Record<string, any>) => void,
   *   insertLocusRag?: (start: number, end: number, attrs: Record<string, any>) => void,
   * }} */
  let {
    selectedPath = "",
    loadingFile = false,
    sourceDirty = false,
    sourceMessage = "",
    savingSource = false,
    deletingSource = false,
    sourceContent = "",
    saveSourceFile = () => {},
    resetSourceEdits = () => {},
    deleteSourceFile = () => {},
    canDeleteSelectedSource = () => false,
    updateSourceDraft = (_event) => {},
    expandSourceEditor = () => {},
    applyFrontmatterFields = (_fields) => {},
    insertLocusRag = (_start, _end, _attrs) => {}
  } = $props();

  let yamlTags = $state("");
  let yamlKeywords = $state("");
  let yamlPriority = $state("");
  let locusKeywords = $state("");
  let locusPriority = $state("");
  let locusTitle = $state("");
  /** @type {HTMLTextAreaElement | null} */
  let textareaElement = $state(null);

  function canEditMetadata() {
    return /^(characters|lore|gm|startings)\//.test(selectedPath || "");
  }

  function canInsertLocusRag() {
    return /^(lore|memory|characters)\//.test(selectedPath || "");
  }

  function applyMetadata() {
    /** @type {Record<string, any>} */
    const fields = {};
    if (yamlTags.trim()) fields.tags = yamlTags.split(",").map((item) => item.trim()).filter(Boolean);
    if (yamlKeywords.trim()) fields.keywords = yamlKeywords.split(",").map((item) => item.trim()).filter(Boolean);
    if (yamlPriority.trim()) fields.priority = Number(yamlPriority);
    applyFrontmatterFields(fields);
  }

  function insertRagTag() {
    const start = textareaElement?.selectionStart ?? sourceContent.length;
    const end = textareaElement?.selectionEnd ?? sourceContent.length;
    insertLocusRag(start, end, {
      keywords: locusKeywords,
      priority: locusPriority,
      title: locusTitle
    });
  }
</script>

{#if loadingFile}
  <p class="notice">ファイルを読み込んでいます。</p>
{:else}
  <div class="prompt-graph-meta">
    <span>path: {selectedPath || "none"}</span>
    {#if sourceDirty}
      <span>unsaved changes</span>
    {/if}
    {#if sourceMessage}
      <span>{sourceMessage}</span>
    {/if}
  </div>
  {#if selectedPath === "state/current.json"}
    <p class="notice state-initial-notice">これはシナリオの初期 State です。新規セッション作成時にコピーされます。セッション中の現在 State はセッション画面の State パネルで確認できます。</p>
  {/if}
  <div class="prompt-editor-actions">
    <button type="button" disabled={savingSource || !sourceDirty} onclick={() => void saveSourceFile()}>
      <Save size={15} aria-hidden="true" /> {savingSource ? "保存中" : "Markdown保存"}
    </button>
    <button type="button" disabled={savingSource || !sourceDirty} onclick={resetSourceEdits}>
      <RotateCcw size={15} aria-hidden="true" /> 変更を破棄
    </button>
    <button
      class="danger-button"
      type="button"
      disabled={savingSource || deletingSource || !canDeleteSelectedSource()}
      title={sourceDirty ? "未保存変更を保存または破棄してから削除してください" : canDeleteSelectedSource() ? "選択中のMarkdownを削除" : "このファイルは削除できません"}
      onclick={() => void deleteSourceFile()}
    >
      <Trash2 size={15} aria-hidden="true" /> {deletingSource ? "削除中" : "削除"}
    </button>
  </div>
  {#if canEditMetadata() || canInsertLocusRag()}
    <div class="source-assist-panel">
      {#if canEditMetadata()}
        <fieldset>
          <legend>Frontmatter</legend>
          <input class="compact-input" bind:value={yamlTags} placeholder="tags: academy, npc" />
          <input class="compact-input" bind:value={yamlKeywords} placeholder="keywords: 旧図書館, 魔導書" />
          <input class="compact-input" bind:value={yamlPriority} type="number" placeholder="priority" />
          <button type="button" disabled={!yamlTags.trim() && !yamlKeywords.trim() && !yamlPriority.trim()} onclick={applyMetadata}>
            <Tags size={14} aria-hidden="true" /> frontmatterへ反映
          </button>
        </fieldset>
      {/if}
      {#if canInsertLocusRag()}
        <fieldset>
          <legend>&lt;locus-rag&gt;</legend>
          <input class="compact-input" bind:value={locusKeywords} placeholder="keywords" />
          <input class="compact-input" bind:value={locusPriority} type="number" placeholder="priority" />
          <input class="compact-input" bind:value={locusTitle} placeholder="title" />
          <button type="button" onclick={insertRagTag}>
            <Tags size={14} aria-hidden="true" /> 選択範囲をRAG化
          </button>
        </fieldset>
      {/if}
    </div>
  {/if}
  <div class="source-editor-wrapper">
    <button
      class="icon-button source-editor-expand"
      type="button"
      title="拡大表示"
      onclick={expandSourceEditor}
    >
      <Maximize2 size={15} aria-hidden="true" />
    </button>
    <textarea
      bind:this={textareaElement}
      class="source-editor"
      value={sourceContent}
      spellcheck="false"
      oninput={updateSourceDraft}
    ></textarea>
  </div>
{/if}

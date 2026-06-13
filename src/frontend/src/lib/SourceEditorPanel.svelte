<script>
  import { Maximize2, RotateCcw, Save, Trash2 } from "lucide-svelte";

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
    expandSourceEditor = () => {}
  } = $props();
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
      disabled={savingSource || deletingSource || sourceDirty || !canDeleteSelectedSource()}
      title={canDeleteSelectedSource() ? "選択中のMarkdownを削除" : "このファイルは削除できません"}
      onclick={() => void deleteSourceFile()}
    >
      <Trash2 size={15} aria-hidden="true" /> {deletingSource ? "削除中" : "削除"}
    </button>
  </div>
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
      class="source-editor"
      value={sourceContent}
      spellcheck="false"
      oninput={updateSourceDraft}
    ></textarea>
  </div>
{/if}

<script>
  import { ChevronDown, ChevronRight, FilePlus2, ListTree, Search, X } from "lucide-svelte";
  import { t } from "../i18n.js";

  /** @type {{
   *   hidden?: boolean,
   *   files?: Array<{ path: string, size?: number }>,
   *   groupedSourceFiles?: Array<{ id: string, labelKey: string, files: Array<{ path: string, size?: number }> }>,
   *   sourceGroupOpen?: Record<string, boolean>,
   *   sourceFilter?: string,
   *   selectedPath?: string,
   *   sourceDirty?: boolean,
   *   loadFile?: (path: string) => Promise<void> | void,
   *   toggleSourceGroup?: (groupId: string) => void,
   *   openCreateFileModal?: (kind?: string) => void,
   * }} */
  let {
    hidden = false,
    files = [],
    groupedSourceFiles = [],
    sourceGroupOpen = {},
    sourceFilter = $bindable(""),
    selectedPath = "",
    sourceDirty = false,
    loadFile = (_path) => {},
    toggleSourceGroup = (_groupId) => {},
    openCreateFileModal = () => {}
  } = $props();

  /**
   * @param {string} groupId
   * @param {Record<string, boolean>} openState
   */
  function isSourceGroupOpen(groupId, openState = sourceGroupOpen) {
    return openState[groupId] !== false;
  }

  /** @param {string} path */
  function sourceDisplayName(path) {
    const parts = path.split("/");
    return parts[parts.length - 1] || path;
  }

  /** @param {string} path */
  function sourceDirectoryLabel(path) {
    const parts = path.split("/");
    return parts.length > 1 ? parts.slice(0, -1).join("/") : "";
  }
</script>

<aside class="panel source-tree" class:hidden aria-labelledby="source-tree-heading">
  <div class="source-tree-header">
    <h3 id="source-tree-heading"><ListTree size={18} aria-hidden="true" /> Vault Tree</h3>
    <button
      class="icon-button compact-icon"
      type="button"
      title={$t("editor.newFile")}
      onclick={() => openCreateFileModal()}
    >
      <FilePlus2 size={16} aria-hidden="true" />
    </button>
  </div>
  <div class="source-filter">
    <Search size={15} aria-hidden="true" />
    <input
      class="compact-input"
      type="search"
      bind:value={sourceFilter}
      placeholder={$t("editor.filterFiles")}
      aria-label={$t("editor.filterFiles")}
    />
    {#if sourceFilter}
      <button class="icon-button compact-icon" type="button" title={$t("common.clear")} onclick={() => (sourceFilter = "")}>
        <X size={14} aria-hidden="true" />
      </button>
    {/if}
  </div>
  {#if files.length}
    <div class="source-groups">
      {#each groupedSourceFiles as group}
        <section class="source-group">
          <div class="source-group-row">
            <button
              class="source-group-toggle"
              class:empty={group.files.length === 0}
              type="button"
              disabled={group.files.length === 0}
              onclick={() => toggleSourceGroup(group.id)}
            >
              {#if isSourceGroupOpen(group.id, sourceGroupOpen)}
                <ChevronDown size={15} aria-hidden="true" />
              {:else}
                <ChevronRight size={15} aria-hidden="true" />
              {/if}
              <strong>{$t(group.labelKey)}</strong>
              <span>{$t("editor.fileCount", { count: group.files.length })}</span>
            </button>
            {#if ["gm", "characters", "lore", "startings"].includes(group.id)}
              <button
                class="icon-button compact-icon source-group-add"
                type="button"
                title={`${$t("editor.newFile")} ${group.id}`}
                onclick={() => openCreateFileModal(group.id)}
              >
                <FilePlus2 size={14} aria-hidden="true" />
              </button>
            {/if}
          </div>
          {#if isSourceGroupOpen(group.id, sourceGroupOpen) && group.files.length}
            <ul class="select-list grouped-select-list">
              {#each group.files as file}
                <li>
                  <button
                    class:selected={file.path === selectedPath}
                    type="button"
                    disabled={sourceDirty}
                    title={sourceDirty ? $t("editor.unsavedWarning") : file.path}
                    onclick={() => loadFile(file.path)}
                  >
                    <strong>{sourceDisplayName(file.path)}</strong>
                    <span>{sourceDirectoryLabel(file.path) || file.path}</span>
                    <span>{file.size || 0} bytes</span>
                  </button>
                </li>
              {/each}
            </ul>
          {/if}
        </section>
      {/each}
      {#if sourceFilter.trim() && groupedSourceFiles.every((group) => group.files.length === 0)}
        <p class="source-empty-copy">{$t("editor.noMatchingFiles")}</p>
      {/if}
    </div>
  {:else}
    <p>{$t("editor.noFiles")}</p>
  {/if}
</aside>

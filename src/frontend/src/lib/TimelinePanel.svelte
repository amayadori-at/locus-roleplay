<script>
  import {
    DEFAULT_GROUP_SIZE,
    ESTIMATED_ROW_HEIGHT,
    VIRTUAL_THRESHOLD,
    buildTimelineRows,
    filterTimelineItems,
    getVirtualWindow,
    normalizeGroupSize,
    normalizedBranches
  } from "./timelineRows.js";
  import { t } from "./i18n.js";

  /** @type {{
   *   items?: Array<Record<string, any>>,
   *   currentSessionId?: string,
   *   metadata?: Record<string, any>,
   *   onJump?: (turn: number, role: string) => void,
   *   onBranch?: (turn: number) => void,
   *   onOpenSession?: (sessionId: string) => void,
   *   onToggleBookmark?: (turn: number, bookmarked: boolean) => void,
   *   onCopySessionId?: (sessionId: string) => void,
   *   onRenameBranch?: (branch: Record<string, any>) => void,
   * }} */
  let {
    items = [],
    currentSessionId = "",
    metadata = {},
    onJump = (turn, role) => {},
    onBranch = (turn) => {},
    onOpenSession = (sessionId) => {},
    onToggleBookmark = (turn, bookmarked) => {},
    onCopySessionId = (sessionId) => {},
    onRenameBranch = (branch) => {}
  } = $props();

  let jumpTurn = $state("");
  let searchText = $state("");
  let bookmarkOnly = $state(false);
  let groupByTurns = $state(true);
  let groupSize = $state(DEFAULT_GROUP_SIZE);
  let toolsOpen = $state(false);
  /** @type {Record<string, boolean>} */
  let collapsedGroups = $state({});
  let viewportElement = $state(/** @type {HTMLDivElement | null} */ (null));
  let scrollTop = $state(0);

  const filteredItems = $derived(filterTimelineItems(items, searchText, bookmarkOnly));
  const normalizedGroupSize = $derived(normalizeGroupSize(groupSize));
  const timelineRows = $derived(buildTimelineRows(filteredItems, groupByTurns ? normalizedGroupSize : 0, collapsedGroups));
  const useVirtualRows = $derived(timelineRows.length > VIRTUAL_THRESHOLD);
  const virtualWindow = $derived(getVirtualWindow(timelineRows.length, scrollTop, viewportElement?.clientHeight || 720, useVirtualRows));
  const visibleRows = $derived(timelineRows.slice(virtualWindow.start, virtualWindow.end));
  const topSpacerHeight = $derived(useVirtualRows ? virtualWindow.start * ESTIMATED_ROW_HEIGHT : 0);
  const bottomSpacerHeight = $derived(useVirtualRows ? Math.max(0, timelineRows.length - virtualWindow.end) * ESTIMATED_ROW_HEIGHT : 0);

  function parentSessionLabel() {
    return metadata.parent_session_id
      ? $t("timeline.parentLabel", { sessionId: metadata.parent_session_id, turn: metadata.branched_from_turn ?? "-" })
      : $t("timeline.parentNone");
  }

  function currentSessionLabel() {
    return metadata.display_name || currentSessionId || "New Session";
  }

  /**
   * @param {Record<string, any>} item
   * @returns {string}
   */
  function getExcerpt(item) {
    const content = item.excerpt || item.content || "";
    return content.length > 60 ? content.slice(0, 60) + "..." : content;
  }

  /** @param {Event} event */
  function handleTimelineScroll(event) {
    scrollTop = event.currentTarget instanceof HTMLElement ? event.currentTarget.scrollTop : 0;
  }

  /** @param {string} key */
  function toggleGroup(key) {
    collapsedGroups = { ...collapsedGroups, [key]: collapsedGroups[key] !== true };
  }

  function handleJumpSubmit() {
    const turn = Number.parseInt(jumpTurn, 10);
    if (!Number.isFinite(turn) || turn < 0) return;
    const item = items.find((entry) => entry.turn === turn) || items.find((entry) => entry.turn >= turn);
    onJump(turn, item?.role || "user");
  }

  /** @param {Record<string, any>} row */
  function rowTurn(row) {
    return row.item?.turn || 0;
  }
</script>

<div class="timeline-origin">
  <span>{$t("timeline.currentSession")}</span>
  <strong>{currentSessionLabel()}</strong>
  <small>{currentSessionId}</small>
  <span>{$t("timeline.parent")}</span>
  <small>{parentSessionLabel()}</small>
  {#if metadata.parent_session_id}
    <button class="tool-button timeline-action" type="button" onclick={() => onOpenSession(metadata.parent_session_id)}>
      {$t("timeline.goParent")}
    </button>
  {/if}
</div>

<div class="timeline-tools-bar">
  <button
    class="tool-button timeline-tools-toggle"
    type="button"
    aria-expanded={toolsOpen}
    onclick={() => toolsOpen = !toolsOpen}
  >
    <span>{$t("timeline.toolsToggle")}</span>
    <span aria-hidden="true">{toolsOpen ? "▲" : "▼"}</span>
  </button>
</div>

<div class="timeline-tools" class:timeline-tools-hidden={!toolsOpen}>
  <label>
    <span>{$t("timeline.turn")}</span>
    <input class="compact-input" type="number" min="0" bind:value={jumpTurn} placeholder={$t("timeline.turnPlaceholder")} />
  </label>
  <button class="tool-button timeline-action" type="button" onclick={handleJumpSubmit}>{$t("timeline.jump")}</button>
  <label class="timeline-search">
    <span>{$t("timeline.search")}</span>
    <input class="compact-input" type="search" bind:value={searchText} placeholder={$t("timeline.searchPlaceholder")} />
  </label>
  <label class="timeline-bookmark-filter">
    <input type="checkbox" bind:checked={bookmarkOnly} />
    <span>{$t("timeline.bookmarkOnly")}</span>
  </label>
  <label class="timeline-group-toggle">
    <input type="checkbox" bind:checked={groupByTurns} />
    <span>{$t("timeline.group")}</span>
  </label>
  <label class="timeline-group-size">
    <span>{$t("timeline.groupSize")}</span>
    <input class="compact-input" type="number" min="1" max="100" bind:value={groupSize} disabled={!groupByTurns} />
  </label>
</div>

<div class="timeline-virtual-viewport" bind:this={viewportElement} onscroll={handleTimelineScroll}>
  <ol class="timeline-list" aria-label={useVirtualRows ? $t("timeline.virtualLabel") : $t("timeline.label")}>
    {#if topSpacerHeight}
      <li class="timeline-spacer" style={`height: ${topSpacerHeight}px`}></li>
    {/if}
    {#each visibleRows as row}
      {#if row.type === "group"}
        <li class:collapsed={row.collapsed} class="timeline-group-row">
          <button class="timeline-group-button" type="button" onclick={() => toggleGroup(row.key)}>
            <span>{row.collapsed ? "▶" : "▼"} {$t("timeline.groupRange", { start: row.start, end: row.end })}</span>
            <small>{$t("timeline.items", { count: row.count })}</small>
          </button>
        </li>
      {:else}
        <li class:bookmarked={row.item.bookmarked} class="timeline-node">
          <div class="timeline-dot" aria-hidden="true"></div>
          <div class="timeline-content">
            <span>{$t("timeline.turn")} {rowTurn(row)}</span>
            <strong>{row.item.role === "assistant" ? $t("timeline.gm") : $t("timeline.user")}</strong>
            <small>{getExcerpt(row.item)}</small>

            <div class="timeline-actions">
              <button
                class:active={row.item.bookmarked}
                class="tool-button timeline-action"
                type="button"
                title={row.item.bookmarked ? $t("timeline.unbookmark") : $t("timeline.bookmark")}
                onclick={() => onToggleBookmark(rowTurn(row), !row.item.bookmarked)}
              >
                {row.item.bookmarked ? "★" : "☆"}
              </button>
              <button class="tool-button timeline-action" type="button" onclick={() => onJump(rowTurn(row), row.item.role)}>{$t("timeline.jumpHere")}</button>
              <button class="tool-button timeline-action" type="button" onclick={() => onBranch(rowTurn(row))}>{$t("timeline.branchHere")}</button>
            </div>
            {#if normalizedBranches(row.item.branches).length}
              <div class="branch-list" aria-label={$t("timeline.branches")}>
                {#each normalizedBranches(row.item.branches) as branch}
                  <div class="branch-item">
                    <strong>{branch.display_name || branch.session_id}</strong>
                    <span>{branch.session_id} / {$t("timeline.turns", { count: branch.turn_count || 0 })}</span>
                    <span>{$t("timeline.branchMeta", { turn: rowTurn(row), state: branch.state_snapshot_available === false ? "fallback" : "snapshot" })}</span>
                    {#if branch.state_snapshot_available === false}
                      <small class="error-copy">{branch.state_snapshot_note || $t("timeline.snapshotFallback")}</small>
                    {/if}
                    <button
                      class="tool-button timeline-action"
                      type="button"
                      onclick={() => branch.session_id && onOpenSession(branch.session_id)}
                    >
                      {$t("timeline.open")}
                    </button>
                    <button
                      class="tool-button timeline-action"
                      type="button"
                      onclick={() => onRenameBranch(branch)}
                    >
                      {$t("timeline.rename")}
                    </button>
                    <button
                      class="tool-button timeline-action"
                      type="button"
                      onclick={() => branch.session_id && onCopySessionId(branch.session_id)}
                    >
                      {$t("timeline.copyId")}
                    </button>
                  </div>
                {/each}
              </div>
            {/if}
          </div>
        </li>
      {/if}
    {/each}
    {#if bottomSpacerHeight}
      <li class="timeline-spacer" style={`height: ${bottomSpacerHeight}px`}></li>
    {/if}
    {#if !filteredItems.length}
      <li class="timeline-empty">{$t("timeline.empty")}</li>
    {/if}
  </ol>
</div>

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

  /** @type {Array<Record<string, any>>} */
  export let items = [];
  export let currentSessionId = "";
  /** @type {Record<string, any>} */
  export let metadata = {};
  /** @type {(turn: number, role: string) => void} */
  export let onJump = (turn, role) => {};
  /** @type {(turn: number) => void} */
  export let onBranch = (turn) => {};
  /** @type {(sessionId: string) => void} */
  export let onOpenSession = (sessionId) => {};
  /** @type {(turn: number, bookmarked: boolean) => void} */
  export let onToggleBookmark = (turn, bookmarked) => {};

  let jumpTurn = "";
  let searchText = "";
  let bookmarkOnly = false;
  let groupByTurns = true;
  let groupSize = DEFAULT_GROUP_SIZE;
  /** @type {Record<string, boolean>} */
  let collapsedGroups = {};
  /** @type {HTMLDivElement | null} */
  let viewportElement = null;
  let scrollTop = 0;

  $: filteredItems = filterTimelineItems(items, searchText, bookmarkOnly);
  $: normalizedGroupSize = normalizeGroupSize(groupSize);
  $: timelineRows = buildTimelineRows(filteredItems, groupByTurns ? normalizedGroupSize : 0, collapsedGroups);
  $: useVirtualRows = timelineRows.length > VIRTUAL_THRESHOLD;
  $: virtualWindow = getVirtualWindow(timelineRows.length, scrollTop, viewportElement?.clientHeight || 720, useVirtualRows);
  $: visibleRows = timelineRows.slice(virtualWindow.start, virtualWindow.end);
  $: topSpacerHeight = useVirtualRows ? virtualWindow.start * ESTIMATED_ROW_HEIGHT : 0;
  $: bottomSpacerHeight = useVirtualRows ? Math.max(0, timelineRows.length - virtualWindow.end) * ESTIMATED_ROW_HEIGHT : 0;

  function parentSessionLabel() {
    return metadata.parent_session_id
      ? `${metadata.parent_session_id} / Turn ${metadata.branched_from_turn ?? "-"} から分岐`
      : "親セッションなし";
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
  <span>現在のセッション</span>
  <strong>{currentSessionLabel()}</strong>
  <small>{currentSessionId}</small>
  <span>親</span>
  <small>{parentSessionLabel()}</small>
  {#if metadata.parent_session_id}
    <button class="tool-button timeline-action" type="button" onclick={() => onOpenSession(metadata.parent_session_id)}>
      親へ移動
    </button>
  {/if}
</div>

<div class="timeline-tools">
  <label>
    <span>Turn</span>
    <input class="compact-input" type="number" min="0" bind:value={jumpTurn} placeholder="番号" />
  </label>
  <button class="tool-button timeline-action" type="button" onclick={handleJumpSubmit}>ジャンプ</button>
  <label class="timeline-search">
    <span>検索</span>
    <input class="compact-input" type="search" bind:value={searchText} placeholder="キーワード" />
  </label>
  <label class="timeline-bookmark-filter">
    <input type="checkbox" bind:checked={bookmarkOnly} />
    <span>Bookmarkのみ</span>
  </label>
  <label class="timeline-group-toggle">
    <input type="checkbox" bind:checked={groupByTurns} />
    <span>Group</span>
  </label>
  <label class="timeline-group-size">
    <span>幅</span>
    <input class="compact-input" type="number" min="1" max="100" bind:value={groupSize} disabled={!groupByTurns} />
  </label>
</div>

<div class="timeline-virtual-viewport" bind:this={viewportElement} onscroll={handleTimelineScroll}>
  <ol class="timeline-list" aria-label={useVirtualRows ? "Timeline virtualized" : "Timeline"}>
    {#if topSpacerHeight}
      <li class="timeline-spacer" style={`height: ${topSpacerHeight}px`}></li>
    {/if}
    {#each visibleRows as row}
      {#if row.type === "group"}
        <li class:collapsed={row.collapsed} class="timeline-group-row">
          <button class="timeline-group-button" type="button" onclick={() => toggleGroup(row.key)}>
            <span>{row.collapsed ? "▶" : "▼"} Turn {row.start}-{row.end}</span>
            <small>{row.count} items</small>
          </button>
        </li>
      {:else}
        <li class:bookmarked={row.item.bookmarked} class="timeline-node">
          <div class="timeline-dot" aria-hidden="true"></div>
          <div class="timeline-content">
            <span>Turn {rowTurn(row)}</span>
            <strong>{row.item.role === "assistant" ? "GM 応答" : "ユーザー発言"}</strong>
            <small>{getExcerpt(row.item)}</small>

            <div class="timeline-actions">
              <button
                class:active={row.item.bookmarked}
                class="tool-button timeline-action"
                type="button"
                title={row.item.bookmarked ? "Bookmark解除" : "Bookmark"}
                onclick={() => onToggleBookmark(rowTurn(row), !row.item.bookmarked)}
              >
                {row.item.bookmarked ? "★" : "☆"}
              </button>
              <button class="tool-button timeline-action" type="button" onclick={() => onJump(rowTurn(row), row.item.role)}>ここへジャンプ</button>
              <button class="tool-button timeline-action" type="button" onclick={() => onBranch(rowTurn(row))}>ここから分岐</button>
            </div>
            {#if normalizedBranches(row.item.branches).length}
              <div class="branch-list" aria-label="派生セッション">
                {#each normalizedBranches(row.item.branches) as branch}
                  <div class="branch-item">
                    <strong>{branch.display_name || branch.session_id}</strong>
                    <span>{branch.session_id} / {branch.turn_count || 0} turns</span>
                    <span>Turn {rowTurn(row)} から分岐</span>
                    <button
                      class="tool-button timeline-action"
                      type="button"
                      onclick={() => branch.session_id && onOpenSession(branch.session_id)}
                    >
                      移動
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
      <li class="timeline-empty">該当するTimeline項目はありません。</li>
    {/if}
  </ol>
</div>

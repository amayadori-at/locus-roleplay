<script>
  import {
    Asterisk,
    Braces,
    ChevronDown,
    ChevronLeft,
    ChevronRight,
    FileStack,
    ImageOff,
    Info,
    Pencil,
    PanelRightOpen,
    RefreshCcw,
    Send,
    Settings,
    Square,
    Trash2,
    Wand2
  } from "lucide-svelte";
  import { formatResponseDuration } from "../sessionLog.js";
  import { renderMarkdown } from "../markdown.js";
  import { t } from "../i18n.js";

  /** @type {{
   *   scenarioId?: string,
   *   isMobile?: boolean,
   *   layout?: any,
   *   preferences?: any,
   *   openSessionInfo?: () => any,
   *   openSessionSettings?: () => any,
   *   chatLogElement?: HTMLElement | null,
   *   handleChatLogScroll?: () => any,
   *   messages?: Array<Record<string, any>>,
   *   logPagination?: Record<string, any>,
   *   loadingOlderLog?: boolean,
   *   sending?: boolean,
   *   loadOlderLog?: () => any,
   *   loadLatestLog?: () => any,
   *   logTurnPageSize?: number,
   *   userLabel?: string,
   *   latestTurn?: number,
   *   resolveUser?: (content: string) => string,
   *   displaySegments?: (message: any) => Array<Record<string, any>>,
   *   expandedMetaSegments?: Record<string, boolean>,
   *   metaSegmentKey?: (message: any, index: number) => string,
   *   toggleMetaSegment?: (key: string) => void,
   *   editMessageTurn?: number | null,
   *   editMessageRole?: string,
   *   editDraft?: string,
   *   editSaving?: boolean,
   *   cancelEditing?: () => any,
   *   saveEdit?: (message: any) => Promise<void> | void,
   *   shouldBranchFromEditedUserMessage?: (message: any) => boolean,
   *   startEditing?: (message: any) => void,
   *   startings?: Array<Record<string, any>>,
   *   sessionMetadata?: Record<string, any>,
   *   switchingStarting?: boolean,
   *   switchStarting?: (direction: "prev" | "next") => Promise<void> | void,
   *   handleContinue?: (message: any) => Promise<void> | void,
   *   handleRegenerate?: (message: any) => Promise<void> | void,
   *   handleDeleteMessage?: (message: any) => Promise<void> | void,
   *   deletingTurn?: number | null,
   *   openBranchDialog?: (turn: number) => void,
   *   handleSwitchCandidate?: (message: any, direction: "prev" | "next") => Promise<void> | void,
   *   turnJobPolling?: boolean,
   *   stateUpdating?: boolean,
   *   newMessageBadge?: boolean,
   *   dismissNewMessageBadge?: () => any,
   *   submitTurn?: () => any,
   *   composer?: HTMLTextAreaElement | null,
   *   input?: string,
   *   currentSessionId?: string,
   *   handleKeydown?: (event: KeyboardEvent) => void,
   *   wrapSelection?: (mode: "quote" | "asterisk") => Promise<void> | void,
   *   stopGeneration?: () => any,
   * }} */
  let {
    scenarioId = "",
    isMobile = false,
    layout,
    preferences,
    openSessionInfo = () => {},
    openSessionSettings = () => {},
    chatLogElement = $bindable(null),
    handleChatLogScroll = () => {},
    messages = [],
    logPagination = {},
    loadingOlderLog = false,
    sending = false,
    loadOlderLog = async () => {},
    loadLatestLog = async () => {},
    logTurnPageSize = 10,
    userLabel = "User",
    latestTurn = -1,
    resolveUser = (content) => content,
    displaySegments = (_message) => [],
    expandedMetaSegments = {},
    metaSegmentKey = (_message, _index) => "",
    toggleMetaSegment = (_key) => {},
    editMessageTurn = null,
    editMessageRole = "",
    editDraft = $bindable(""),
    editSaving = false,
    cancelEditing = () => {},
    saveEdit = (_message) => {},
    shouldBranchFromEditedUserMessage = (_message) => false,
    startEditing = (_message) => {},
    startings = [],
    sessionMetadata = {},
    switchingStarting = false,
    switchStarting = (_direction) => {},
    handleContinue = (_message) => {},
    handleRegenerate = (_message) => {},
    handleDeleteMessage = (_message) => {},
    deletingTurn = null,
    openBranchDialog = (_turn) => {},
    handleSwitchCandidate = (_message, _direction) => {},
    turnJobPolling = false,
    stateUpdating = false,
    newMessageBadge = false,
    dismissNewMessageBadge = async () => {},
    submitTurn = async () => {},
    composer = $bindable(null),
    input = $bindable(""),
    currentSessionId = "",
    handleKeydown = (_event) => {},
    wrapSelection = (_mode) => {},
    stopGeneration = () => {}
  } = $props();

</script>

<section class="panel chat-panel" aria-labelledby="chat-heading">
  <div class="panel-header compact">
    <h3 id="chat-heading">Chat</h3>
    <div class="chat-top-tools" aria-label={$t("session.sessionOps")}>
      <span>{scenarioId || $t("session.noScenarioId")}</span>
      {#if !isMobile && !$layout.rightOpen}
        <button class="icon-button" type="button" title={$t("session.openRightPanel")} aria-label={$t("session.openRightPanel")} onclick={() => layout.setRightOpen(true)}>
          <PanelRightOpen size={17} aria-hidden="true" />
        </button>
      {/if}
      <button class="icon-button" type="button" title={$t("session.sessionInfo")} aria-label={$t("session.sessionInfo")} onclick={openSessionInfo}>
        <Info size={17} aria-hidden="true" />
      </button>
      <button class="icon-button" type="button" title={$t("session.sessionSettings")} aria-label={$t("session.sessionSettings")} onclick={openSessionSettings}>
        <Settings size={17} aria-hidden="true" />
      </button>
    </div>
  </div>

  <div class="chat-log" aria-live="polite" bind:this={chatLogElement} onscroll={handleChatLogScroll}>
    {#if messages.length}
      {#if logPagination.has_more_before}
        <div class="log-page-controls">
          <button class="tool-button" type="button" disabled={loadingOlderLog || sending} onclick={() => void loadOlderLog()}>
            {loadingOlderLog ? $t("session.loadingMore") : $t("session.loadOlderTurns", { count: logTurnPageSize })}
          </button>
          <span>
            Turn {logPagination.min_turn ?? "-"}-{logPagination.max_turn ?? "-"} / {logPagination.total_turns ?? "-"} turns
          </span>
        </div>
      {/if}
      {#each messages as message}
        <article id="message-turn-{message.turn}-{message.role}" class:assistant-message={message.role === "assistant"} class="chat-message">
          <div class="message-bubble">
            <header>
              <span>{message.role === "assistant" ? "GM" : userLabel}</span>
              <span class="message-meta-line">
                {#if message.turn}
                  <span>Turn {message.turn}</span>
                {/if}
                {#if message.role === "assistant" && formatResponseDuration(message)}
                  <span title="RAG / RP / State response time">{formatResponseDuration(message)}</span>
                {/if}
              </span>
            </header>
            {#if editMessageTurn === message.turn && editMessageRole === message.role}
              <div class="message-editor" style="margin-top: 8px;">
                <textarea class="settings-textarea" bind:value={editDraft} rows={Math.max(3, (editDraft || "").split("\n").length)}></textarea>
                <div class="editor-actions memory-actions" style="margin-top: 8px; justify-content: flex-end;">
                  <button class="tool-button" type="button" disabled={editSaving} onclick={cancelEditing}>{$t("common.cancel")}</button>
                  <button class="primary-button" type="button" disabled={editSaving} onclick={() => saveEdit(message)}>
                    {shouldBranchFromEditedUserMessage(message) ? $t("session.branchAndLoad") : $t("common.saveChanges")}
                  </button>
                </div>
              </div>
            {:else if displaySegments(message).length}
              <div class="message-segments">
                {#each displaySegments(message) as segment, segmentIndex}
                  {#if segment.type === "image"}
                    {#if segment.url && segment.exists !== false}
                      <img src={segment.url} alt={segment.path || "scenario image"} loading="lazy" />
                    {:else}
                      <span class="missing-image">
                        <ImageOff size={16} aria-hidden="true" />
                        {segment.path || "missing image"}
                      </span>
                  {/if}
                {:else if segment.type === "character_dialogue"}
                  <div class="bustup-dialogue">
                    <img src={segment.character.bustup_url} alt={segment.speaker} loading="lazy" />
                    <div class="dialogue-bubble">
                      <strong>{segment.speaker}</strong>
                      <div class="markdown-body">{@html renderMarkdown(resolveUser(segment.dialogue))}</div>
                    </div>
                  </div>
                {:else if segment.type === "meta"}
                  <div class="meta-segment">
                    {#if segment.live}
                      <div class="meta-live-label">{$t("session.reasoning")}<span class="loading-dots" aria-hidden="true"></span></div>
                      <div class="meta-content meta-content--live markdown-body">
                        {@html renderMarkdown(resolveUser(segment.content))}
                      </div>
                    {:else}
                      <button
                        class="meta-toggle"
                        type="button"
                        aria-expanded={expandedMetaSegments[metaSegmentKey(message, segmentIndex)] === true ? "true" : "false"}
                        onclick={() => toggleMetaSegment(metaSegmentKey(message, segmentIndex))}
                      >
                        {expandedMetaSegments[metaSegmentKey(message, segmentIndex)] === true ? $t("session.hideReasoning") : $t("session.showReasoning")}
                      </button>
                      {#if expandedMetaSegments[metaSegmentKey(message, segmentIndex)] === true}
                        <div class="meta-content markdown-body">
                          {@html renderMarkdown(resolveUser(segment.content))}
                        </div>
                      {/if}
                    {/if}
                  </div>
                {:else}
                    <div class="markdown-body">{@html renderMarkdown(resolveUser(segment.content))}</div>
                {/if}
              {/each}
              {#if message.streaming}
                <div class="stream-loading-indicator" aria-label={$t("session.waitingGM")}>
                  <Wand2 size={15} aria-hidden="true" />
                  <span>{message.content ? $t("session.generating") : $t("session.waitingStream")}</span>
                  <span class="loading-dots" aria-hidden="true"></span>
                </div>
              {/if}
            </div>
          {/if}
        </div>
          <div class="message-actions" aria-label={message.role === "assistant" ? $t("session.gmActions") : $t("session.userActions")}>
            {#if message.role === "assistant"}
              {#if message.is_starting}
                {#if startings.length > 1 && (sessionMetadata?.turn_count ?? 1) === 0}
                  <div class="candidate-switcher" aria-label={$t("session.switchStartingLabel")}>
                    <button class="icon-button message-action-button" type="button" title={$t("session.prevStarting")} aria-label={$t("session.prevStarting")} disabled={switchingStarting} onclick={() => void switchStarting("prev")}>
                      <ChevronLeft size={15} aria-hidden="true" />
                    </button>
                    <span>{startings.findIndex((/** @type {any} */ s) => s.id === message.starting_id) + 1}/{startings.length}</span>
                    <button class="icon-button message-action-button" type="button" title={$t("session.nextStarting")} aria-label={$t("session.nextStarting")} disabled={switchingStarting} onclick={() => void switchStarting("next")}>
                      <ChevronRight size={15} aria-hidden="true" />
                    </button>
                  </div>
                {/if}
              {:else}
                {#if message.turn === latestTurn}
                  <button class="icon-button message-action-button" type="button" title={$t("session.continueGen")} aria-label={$t("session.continueGen")} disabled={sending} onclick={() => handleContinue(message)}>
                    <ChevronDown size={15} aria-hidden="true" />
                  </button>
                  <button class="icon-button message-action-button" type="button" title={$t("session.regenerate")} aria-label={$t("session.regenerate")} disabled={sending} onclick={() => handleRegenerate(message)}>
                    <RefreshCcw size={15} aria-hidden="true" />
                  </button>
                  <button class="icon-button message-action-button" type="button" title={$t("session.delete")} aria-label={$t("session.delete")} disabled={deletingTurn === message.turn} onclick={() => handleDeleteMessage(message)}>
                    <Trash2 size={15} aria-hidden="true" />
                  </button>
                {/if}
                <button class="icon-button message-action-button" type="button" title={$t("session.edit")} aria-label={$t("session.edit")} onclick={() => startEditing(message)}>
                  <Pencil size={15} aria-hidden="true" />
                </button>
                <button
                  class="icon-button message-action-button"
                  type="button"
                  title={$t("session.branchFromHere")}
                  aria-label={$t("session.branchFromHere")}
                  disabled={sending || message.turn == null}
                  onclick={() => message.turn != null && openBranchDialog(message.turn)}
                >
                  <FileStack size={15} aria-hidden="true" />
                </button>
                {#if message.candidates && message.candidates.length > 1}
                  <div class="candidate-switcher" aria-label={$t("session.switchCandidate")}>
                    <button class="icon-button message-action-button" type="button" title={$t("session.prevCandidate")} aria-label={$t("session.prevCandidate")} onclick={() => handleSwitchCandidate(message, "prev")}>
                      <ChevronLeft size={15} aria-hidden="true" />
                    </button>
                    <span>{(message.active_candidate_index || 0) + 1}/{message.candidates.length}</span>
                    <button class="icon-button message-action-button" type="button" title={$t("session.nextCandidate")} aria-label={$t("session.nextCandidate")} onclick={() => handleSwitchCandidate(message, "next")}>
                      <ChevronRight size={15} aria-hidden="true" />
                    </button>
                  </div>
                {/if}
              {/if}
            {:else}
              {#if message.turn === latestTurn}
                <button class="icon-button message-action-button" type="button" title={$t("session.delete")} aria-label={$t("session.delete")} disabled={deletingTurn === message.turn} onclick={() => handleDeleteMessage(message)}>
                  <Trash2 size={15} aria-hidden="true" />
                </button>
              {/if}
              <button class="icon-button message-action-button" type="button" title={$t("session.edit")} aria-label={$t("session.edit")} onclick={() => startEditing(message)}>
                <Pencil size={15} aria-hidden="true" />
              </button>
            {/if}
          </div>
        </article>
      {/each}
      {#if logPagination.has_more_after}
        <div class="log-page-controls">
          <button class="tool-button" type="button" disabled={loadingOlderLog || sending} onclick={() => void loadLatestLog()}>
            {$t("session.latestTurn")}
          </button>
          <span>
            Turn {logPagination.min_turn ?? "-"}-{logPagination.max_turn ?? "-"} / {logPagination.total_turns ?? "-"} turns
          </span>
        </div>
      {/if}
    {:else}
      <p class="notice">{$t("session.noLog")}</p>
    {/if}
    {#if sending && (!$preferences.streamEnabled || turnJobPolling)}
      <div class="inline-loading-indicator" aria-label={$t("session.generatingResponse")}>
        <Wand2 size={16} aria-hidden="true" />
        <span>{$t("session.generatingResponse")}</span>
        <span class="loading-dots" aria-hidden="true"></span>
      </div>
    {/if}
    {#if stateUpdating}
      <div class="inline-loading-indicator" aria-label={$t("session.updatingState")}>
        <Wand2 size={16} aria-hidden="true" />
        <span>{$t("session.updatingState")}</span>
        <span class="loading-dots" aria-hidden="true"></span>
      </div>
    {/if}
  </div>

  {#if newMessageBadge}
    <div class="new-message-badge-bar">
      <button class="new-message-badge" type="button" onclick={() => void dismissNewMessageBadge()}>
        <ChevronDown size={14} aria-hidden="true" /> {$t("session.newMessages")}
      </button>
    </div>
  {/if}

  <form class="composer" onsubmit={(event) => { event.preventDefault(); void submitTurn(); }}>
    <div class="textarea-wrapper">
      <textarea
        bind:this={composer}
        bind:value={input}
        disabled={!currentSessionId || sending || stateUpdating}
        placeholder={currentSessionId ? $t("session.inputPlaceholder") : $t("session.creatingSessionPlaceholder")}
        rows="1"
        onkeydown={handleKeydown}
      ></textarea>
      <div class="composer-tools-inline">
        <button type="button" title="「」" onclick={() => wrapSelection("quote")}>
          <Braces size={16} aria-hidden="true" />
        </button>
        <button type="button" title="*" onclick={() => wrapSelection("asterisk")}>
          <Asterisk size={16} aria-hidden="true" />
        </button>
      </div>
    </div>
    <div class="composer-footer-actions">
      <label class="send-mode-toggle" title={sending ? $t("session.streamToggleSending") : $t("session.streamToggleTitle")}>
        <input type="checkbox" checked={$preferences.streamEnabled} disabled={sending || stateUpdating} onchange={(event) => preferences.setStreamEnabled(event.currentTarget.checked)} />
        <span>Stream</span>
      </label>
      <label class="send-mode-toggle" title={$t("session.enterToggleTitle")}>
        <input type="checkbox" checked={$preferences.sendOnEnter} onchange={(event) => preferences.setSendOnEnter(event.currentTarget.checked)} />
        <span>{$t("session.sendOnEnter")}</span>
      </label>
      <button
        class="send-button"
        type={sending ? "button" : "submit"}
        disabled={!currentSessionId || stateUpdating || (!sending && !input.trim())}
        onclick={() => sending && stopGeneration()}
      >
        {#if sending}
          <Square size={16} aria-hidden="true" />
          {$t("session.stop")}
        {:else}
          <Send size={16} aria-hidden="true" />
          {$t("session.send")}
        {/if}
      </button>
    </div>
  </form>
</section>

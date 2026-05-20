<script>
  import {
    CheckSquare,
    ChevronDown,
    Clock,
    CornerDownRight,
    FilePenLine,
    FilePlus2,
    GitBranch,
    Image,
    Layers,
    Maximize2,
    Pencil,
    Play,
    RotateCcw,
    Trash2,
    X
  } from "lucide-svelte";
  import { onMount } from "svelte";
  import { createScenario, deleteSession, listScenarioSessions, listScenarios, updateSessionSettings } from "../lib/api.js";
  import { renderMarkdown } from "../lib/markdown.js";

  /**
   * @type {{
   *   openSession: (scenarioId: string, sessionId?: string) => void,
   *   openScenarioEdit: (scenarioId: string, sourcePath?: string) => void
   * }}
   */
  export let onNavigate = {
    openSession: () => {},
    openScenarioEdit: () => {}
  };

  /**
   * @typedef {{
   *   session_id: string,
   *   display_name?: string,
   *   updated_at?: string,
   *   turn_count?: number,
   *   parent_session_id?: string,
   *   branched_from_turn?: number
   * }} SessionSummary
   */

  /**
   * @typedef {{
   *   session: SessionSummary,
   *   children: SessionTreeNode[],
   *   orphan: boolean
   * }} SessionTreeNode
   */

  /**
   * @typedef {{
   *   session: SessionSummary,
   *   depth: number,
   *   child_count: number,
   *   orphan: boolean
   * }} FlatSessionTreeNode
   */

  /** @type {Array<{ id: string, name?: string, description?: string, metadata?: Record<string, unknown> }>} */
  let scenarios = [];
  /** @type {{ id: string, name?: string, description?: string, metadata?: Record<string, unknown> } | null} */
  let activeScenario = null;
  /** @type {SessionSummary[]} */
  let sessions = [];
  /** @type {FlatSessionTreeNode[]} */
  let sessionTree = [];
  let selectedScenarioId = "";
  let loadingScenarios = true;
  let loadingSessions = false;
  let descriptionModalOpen = false;
  let scenarioError = "";
  let sessionError = "";
  let bulkDeleteMode = false;
  let sessionTreeOpen = false;
  /** @type {Set<string>} */
  let selectedSessionIds = new Set();
  let renamingSessionId = "";
  let renameDraft = "";
  let sessionActionBusy = false;
  let creatingScenario = false;
  let createScenarioModalOpen = false;
  let newScenarioId = "";
  let newScenarioName = "";
  let newScenarioDescription = "";
  let createScenarioError = "";

  onMount(async () => {
    await loadScenarios();
  });

  $: sessionTree = buildSessionTree(sessions);

  async function loadScenarios() {
    loadingScenarios = true;
    scenarioError = "";
    try {
      const payload = await listScenarios();
      scenarios = payload.scenarios || [];
      selectedScenarioId = scenarios[0]?.id || "";
      activeScenario = scenarios[0] || null;
      if (selectedScenarioId) {
        await loadSessions(selectedScenarioId);
      }
    } catch (caught) {
      scenarioError = caught instanceof Error ? caught.message : "シナリオ一覧を読み込めませんでした。";
    } finally {
      loadingScenarios = false;
    }
  }

  /** @param {string} scenarioId */
  async function selectScenario(scenarioId) {
    if (selectedScenarioId === scenarioId) {
      return;
    }
    selectedScenarioId = scenarioId;
    activeScenario = scenarios.find((scenario) => scenario.id === scenarioId) || null;
    sessionTreeOpen = false;
    await loadSessions(scenarioId);
  }

  /** @param {string} scenarioId */
  async function loadSessions(scenarioId) {
    loadingSessions = true;
    sessionError = "";
    sessions = [];
    selectedSessionIds = new Set();
    bulkDeleteMode = false;
    renamingSessionId = "";
    try {
      const payload = await listScenarioSessions(scenarioId);
      sessions = payload.sessions || [];
    } catch (caught) {
      sessionError = caught instanceof Error ? caught.message : "セッション一覧を読み込めませんでした。";
    } finally {
      loadingSessions = false;
    }
  }

  /** @param {unknown} value */
  function displayValue(value) {
    if (value === undefined || value === null || value === "") {
      return "未設定";
    }
    if (typeof value === "boolean") {
      return value ? "true" : "false";
    }
    return String(value);
  }

  /** @param {string | undefined} value */
  function displayDate(value) {
    if (!value) {
      return "updated 不明";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }
    return new Intl.DateTimeFormat("ja-JP", {
      dateStyle: "medium",
      timeStyle: "short"
    }).format(date);
  }

  /** @param {SessionSummary[]} sessionItems */
  function buildSessionTree(sessionItems) {
    /** @type {Map<string, SessionTreeNode>} */
    const byId = new Map();
    /** @type {SessionTreeNode[]} */
    const roots = [];
    /** @type {FlatSessionTreeNode[]} */
    const flattened = [];

    for (const session of sessionItems) {
      byId.set(session.session_id, { session, children: [], orphan: false });
    }

    for (const node of byId.values()) {
      const parentId = node.session.parent_session_id;
      if (parentId && byId.has(parentId)) {
        const parent = byId.get(parentId);
        if (parent) {
          parent.children.push(node);
        }
      } else {
        node.orphan = Boolean(parentId);
        roots.push(node);
      }
    }

    /**
     * @param {SessionTreeNode} left
     * @param {SessionTreeNode} right
     */
    const compareNodes = (left, right) => {
      const leftTurn = typeof left.session.branched_from_turn === "number" ? left.session.branched_from_turn : -1;
      const rightTurn = typeof right.session.branched_from_turn === "number" ? right.session.branched_from_turn : -1;
      if (leftTurn !== rightTurn) {
        return leftTurn - rightTurn;
      }
      return (left.session.display_name || left.session.session_id).localeCompare(
        right.session.display_name || right.session.session_id,
        "ja"
      );
    };

    /**
     * @param {SessionTreeNode} node
     * @param {number} depth
     */
    const visit = (node, depth) => {
      node.children.sort(compareNodes);
      flattened.push({
        session: node.session,
        depth,
        child_count: node.children.length,
        orphan: node.orphan
      });
      for (const child of node.children) {
        visit(child, depth + 1);
      }
    };

    roots.sort(compareNodes);
    for (const root of roots) {
      visit(root, 0);
    }

    return flattened;
  }

  /** @param {string} sessionId */
  function toggleSessionSelection(sessionId) {
    const next = new Set(selectedSessionIds);
    if (next.has(sessionId)) {
      next.delete(sessionId);
    } else {
      next.add(sessionId);
    }
    selectedSessionIds = next;
  }

  function toggleBulkDeleteMode() {
    bulkDeleteMode = !bulkDeleteMode;
    selectedSessionIds = new Set();
    renamingSessionId = "";
  }

  /** @param {{ session_id: string, display_name?: string }} session */
  function startRename(session) {
    renamingSessionId = session.session_id;
    renameDraft = session.display_name || session.session_id;
    bulkDeleteMode = false;
  }

  function cancelRename() {
    renamingSessionId = "";
    renameDraft = "";
  }

  /** @param {string} sessionId */
  async function saveRename(sessionId) {
    const displayName = renameDraft.trim();
    if (!selectedScenarioId || !displayName || sessionActionBusy) {
      return;
    }
    sessionActionBusy = true;
    sessionError = "";
    try {
      await updateSessionSettings(selectedScenarioId, sessionId, { display_name: displayName });
      await loadSessions(selectedScenarioId);
    } catch (caught) {
      sessionError = caught instanceof Error ? caught.message : "セッション名を変更できませんでした。";
    } finally {
      sessionActionBusy = false;
    }
  }

  /** @param {string} sessionId */
  async function removeSession(sessionId) {
    if (!selectedScenarioId || sessionActionBusy) {
      return;
    }
    const sessionName = sessions.find((session) => session.session_id === sessionId)?.display_name || sessionId;
    if (!window.confirm(`「${sessionName}」を削除します。この操作は元に戻せません。`)) {
      return;
    }
    sessionActionBusy = true;
    sessionError = "";
    try {
      await deleteSession(selectedScenarioId, sessionId);
      await loadSessions(selectedScenarioId);
    } catch (caught) {
      sessionError = caught instanceof Error ? caught.message : "セッションを削除できませんでした。";
    } finally {
      sessionActionBusy = false;
    }
  }

  async function removeSelectedSessions() {
    if (!selectedScenarioId || !selectedSessionIds.size || sessionActionBusy) {
      return;
    }
    const count = selectedSessionIds.size;
    if (!window.confirm(`${count}件のセッションを削除します。この操作は元に戻せません。`)) {
      return;
    }
    sessionActionBusy = true;
    sessionError = "";
    try {
      for (const sessionId of selectedSessionIds) {
        await deleteSession(selectedScenarioId, sessionId);
      }
      selectedSessionIds = new Set();
      bulkDeleteMode = false;
      await loadSessions(selectedScenarioId);
    } catch (caught) {
      sessionError = caught instanceof Error ? caught.message : "選択したセッションを削除できませんでした。";
    } finally {
      sessionActionBusy = false;
    }
  }

  function validateNewScenarioInput() {
    const scenarioId = newScenarioId.trim();
    if (!/^[A-Za-z0-9_-]+$/.test(scenarioId)) {
      return "Scenario ID は半角英数字、underscore、hyphen のみで入力してください。";
    }
    if (!newScenarioName.trim()) {
      return "表示名を入力してください。";
    }
    if (scenarios.some((scenario) => scenario.id === scenarioId)) {
      return "同じ ID のシナリオが既に存在します。";
    }
    return "";
  }

  function openCreateScenarioModal() {
    createScenarioModalOpen = true;
    createScenarioError = "";
  }

  function closeCreateScenarioModal() {
    if (creatingScenario) {
      return;
    }
    createScenarioModalOpen = false;
    createScenarioError = "";
  }

  async function createNewScenario() {
    if (creatingScenario) {
      return;
    }
    createScenarioError = validateNewScenarioInput();
    if (createScenarioError) {
      return;
    }
    creatingScenario = true;
    scenarioError = "";
    try {
      const scenarioId = newScenarioId.trim();
      const payload = await createScenario({
        scenario_id: scenarioId,
        name: newScenarioName.trim(),
        description: newScenarioDescription
      });
      const listPayload = await listScenarios();
      scenarios = listPayload.scenarios || [];
      selectedScenarioId = payload.scenario?.id || scenarioId;
      activeScenario = scenarios.find((scenario) => scenario.id === selectedScenarioId) || payload.scenario || null;
      sessions = [];
      newScenarioId = "";
      newScenarioName = "";
      newScenarioDescription = "";
      createScenarioError = "";
      createScenarioModalOpen = false;
      onNavigate.openScenarioEdit(selectedScenarioId, "scenario.md");
    } catch (caught) {
      createScenarioError = caught instanceof Error ? caught.message : "シナリオを作成できませんでした。";
    } finally {
      creatingScenario = false;
    }
  }
</script>

<div class="toolbar">
  <div>
    <p class="eyebrow">Front Page</p>
    <h2 id="workspace-heading">Scenarios</h2>
  </div>
</div>

{#if scenarioError}
  <p class="notice">{scenarioError}</p>
{:else if loadingScenarios}
  <p class="notice">シナリオ一覧を読み込んでいます。</p>
{:else}
  <div class="front-layout">
    <section class="panel" aria-labelledby="scenario-list-heading">
      <div class="source-tree-header">
        <h3 id="scenario-list-heading"><Layers size={18} aria-hidden="true" /> Scenario List</h3>
        <button
          class="icon-button compact-icon"
          type="button"
          title="新規シナリオ作成"
          onclick={openCreateScenarioModal}
        >
          <FilePlus2 size={16} aria-hidden="true" />
        </button>
      </div>
      {#if scenarios.length}
        <ul class="select-list">
          {#each scenarios as scenario}
            <li>
              <button
                class:selected={scenario.id === selectedScenarioId}
                type="button"
                onclick={() => selectScenario(scenario.id)}
              >
                <strong>{scenario.name || scenario.id}</strong>
                <span>{scenario.id}</span>
              </button>
            </li>
          {/each}
        </ul>
      {:else}
        <p>シナリオがありません。</p>
      {/if}
    </section>

    {#if activeScenario}
      <section class="panel scenario-detail" aria-labelledby="scenario-detail-heading">
        <div class="panel-header">
          <div>
            <p class="eyebrow">Selected Scenario</p>
            <h3 id="scenario-detail-heading">{activeScenario.name || activeScenario.id}</h3>
          </div>
          <button
            class="icon-button"
            type="button"
            title="Scenario Edit"
            onclick={() => onNavigate.openScenarioEdit(selectedScenarioId)}
          >
            <FilePenLine size={18} aria-hidden="true" />
          </button>
        </div>

        <div class="meta-row">
          <span><Image size={15} aria-hidden="true" /> image: {displayValue(activeScenario.metadata?.image_mode)}</span>
          <span><Clock size={15} aria-hidden="true" /> sessions: {sessions.length}</span>
          <span>ID: {activeScenario.id}</span>
        </div>

        <div class="description-row">
          <div class="description markdown-body">{@html renderMarkdown(activeScenario.description || "説明文はありません。")}</div>
          <button class="icon-button description-expand" type="button" title="拡大表示" onclick={() => (descriptionModalOpen = true)}>
            <Maximize2 size={15} aria-hidden="true" />
          </button>
        </div>

        <div class="actions">
          <button type="button" onclick={() => onNavigate.openSession(selectedScenarioId)}>
            <Play size={16} aria-hidden="true" /> 開始
          </button>
          <button type="button" onclick={() => loadSessions(selectedScenarioId)}>
            <RotateCcw size={16} aria-hidden="true" /> 再読込
          </button>
        </div>

        <section class="session-area" aria-labelledby="session-list-heading">
          <div class="panel-header compact">
            <h4 id="session-list-heading">Sessions</h4>
            <div class="session-toolbar">
              <span>{loadingSessions ? "Loading" : `${sessions.length} items`}</span>
              {#if sessions.length}
                <button
                  class:active={bulkDeleteMode}
                  type="button"
                  disabled={sessionActionBusy}
                  onclick={toggleBulkDeleteMode}
                >
                  <CheckSquare size={15} aria-hidden="true" /> 一括削除
                </button>
              {/if}
            </div>
          </div>

          {#if bulkDeleteMode}
            <div class="bulk-action-bar">
              <span>{selectedSessionIds.size}件選択中</span>
              <button type="button" disabled={!selectedSessionIds.size || sessionActionBusy} onclick={() => void removeSelectedSessions()}>
                <Trash2 size={15} aria-hidden="true" /> 選択を削除
              </button>
              <button type="button" disabled={sessionActionBusy} onclick={toggleBulkDeleteMode}>キャンセル</button>
            </div>
          {/if}

          {#if sessionError}
            <p class="notice">{sessionError}</p>
          {:else if loadingSessions}
            <p class="notice">セッション一覧を読み込んでいます。</p>
          {:else if sessions.length}
            <ul class:bulk-delete-mode={bulkDeleteMode} class="session-list">
              {#each sessions as session}
                <li>
                  {#if bulkDeleteMode}
                    <label class="session-check" title="削除対象に選択">
                      <input
                        type="checkbox"
                        checked={selectedSessionIds.has(session.session_id)}
                        onchange={() => toggleSessionSelection(session.session_id)}
                      />
                    </label>
                  {/if}
                  <div>
                    {#if renamingSessionId === session.session_id}
                      <div class="rename-row">
                        <input
                          bind:value={renameDraft}
                          aria-label="セッション表示名"
                          onkeydown={(event) => {
                            if (event.key === "Enter") void saveRename(session.session_id);
                            if (event.key === "Escape") cancelRename();
                          }}
                        />
                        <button type="button" disabled={sessionActionBusy || !renameDraft.trim()} onclick={() => void saveRename(session.session_id)}>保存</button>
                        <button type="button" disabled={sessionActionBusy} onclick={cancelRename}>取消</button>
                      </div>
                    {:else}
                      <strong>{session.display_name || session.session_id}</strong>
                    {/if}
                    <span>{session.session_id}</span>
                  </div>
                  <div class="session-meta">
                    <span>{displayDate(session.updated_at)}</span>
                    <span>{session.turn_count || 0} turns</span>
                  </div>
                  <div class="session-actions">
                    <button
                      type="button"
                      disabled={bulkDeleteMode || sessionActionBusy}
                      onclick={() => onNavigate.openSession(selectedScenarioId, session.session_id)}
                    >
                      再開
                    </button>
                    <button
                      class="icon-button compact-icon"
                      type="button"
                      title="改名"
                      disabled={bulkDeleteMode || sessionActionBusy}
                      onclick={() => startRename(session)}
                    >
                      <Pencil size={15} aria-hidden="true" />
                    </button>
                    <button
                      class="icon-button compact-icon danger-button"
                      type="button"
                      title="削除"
                      disabled={bulkDeleteMode || sessionActionBusy}
                      onclick={() => void removeSession(session.session_id)}
                    >
                      <Trash2 size={15} aria-hidden="true" />
                    </button>
                  </div>
                </li>
              {/each}
            </ul>
          {:else}
            <p class="notice">このシナリオにはまだセッションがありません。</p>
          {/if}
        </section>

        <section class="session-tree-area" aria-labelledby="session-tree-heading">
          <div class="panel-header compact session-tree-accordion-header">
            <h4 id="session-tree-heading"><GitBranch size={16} aria-hidden="true" /> 全体管理 / セッションツリー</h4>
            <button
              class="session-tree-toggle"
              type="button"
              aria-expanded={sessionTreeOpen}
              aria-controls="session-tree-content"
              onclick={() => (sessionTreeOpen = !sessionTreeOpen)}
            >
              <span>{loadingSessions ? "Loading" : `${sessionTree.length} nodes`}</span>
              <ChevronDown size={16} aria-hidden="true" />
            </button>
          </div>

          {#if sessionTreeOpen}
            <div id="session-tree-content" class="session-tree-accordion-body">
              {#if sessionError}
                <p class="notice">{sessionError}</p>
              {:else if loadingSessions}
                <p class="notice">セッションツリーを読み込んでいます。</p>
              {:else if sessionTree.length}
                <ul class="session-tree-list">
                  {#each sessionTree as node}
                    <li class:branch-node={node.depth > 0} class:orphan-node={node.orphan}>
                      <div class="tree-node-main" style={`--tree-depth: ${node.depth}`}>
                        <span class="tree-line-icon" aria-hidden="true">
                          {#if node.depth > 0}
                            <CornerDownRight size={15} />
                          {:else}
                            <GitBranch size={15} />
                          {/if}
                        </span>
                        <div class="tree-node-text">
                          <strong>{node.session.display_name || node.session.session_id}</strong>
                          <span>{node.session.session_id}</span>
                          {#if node.session.parent_session_id}
                            <small>
                              {node.orphan ? "親session未検出" : `Turn ${node.session.branched_from_turn ?? "-"} から分岐`}
                              / parent: {node.session.parent_session_id}
                            </small>
                          {:else}
                            <small>root session{node.child_count ? ` / ${node.child_count} branches` : ""}</small>
                          {/if}
                        </div>
                      </div>
                      <div class="tree-node-meta">
                        <span>{displayDate(node.session.updated_at)}</span>
                        <span>{node.session.turn_count || 0} turns</span>
                      </div>
                      <button
                        type="button"
                        disabled={sessionActionBusy}
                        onclick={() => onNavigate.openSession(selectedScenarioId, node.session.session_id)}
                      >
                        再開
                      </button>
                    </li>
                  {/each}
                </ul>
              {:else}
                <p class="notice">このシナリオにはまだセッションツリーがありません。</p>
              {/if}
            </div>
          {/if}
        </section>
      </section>
    {/if}
  </div>
{/if}

{#if createScenarioModalOpen}
  <div class="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="create-scenario-modal-heading">
    <button class="modal-scrim" type="button" aria-label="閉じる" onclick={closeCreateScenarioModal}></button>
    <div class="picker-modal create-source-modal">
      <div class="panel-header compact">
        <h3 id="create-scenario-modal-heading"><FilePlus2 size={16} aria-hidden="true" /> 新規シナリオ作成</h3>
        <button class="icon-button" type="button" title="閉じる" disabled={creatingScenario} onclick={closeCreateScenarioModal}>
          <X size={18} aria-hidden="true" />
        </button>
      </div>

      <label>
        <span>Scenario ID</span>
        <input class="compact-input" bind:value={newScenarioId} placeholder="new_arc" />
      </label>
      <label>
        <span>Name</span>
        <input class="compact-input" bind:value={newScenarioName} placeholder="新しいシナリオ" />
      </label>
      <label>
        <span>Description</span>
        <textarea class="compact-input" rows="4" bind:value={newScenarioDescription} placeholder="最小テンプレートに入れる説明"></textarea>
      </label>
      <small class="source-path-preview">
        rp/scenarios/{newScenarioId.trim() || "<scenario_id>"}/
      </small>

      {#if createScenarioError}
        <p class="mini-error">{createScenarioError}</p>
      {/if}

      <div class="modal-row-actions">
        <button
          type="button"
          disabled={creatingScenario || !newScenarioId.trim() || !newScenarioName.trim()}
          onclick={() => void createNewScenario()}
        >
          <FilePlus2 size={15} aria-hidden="true" /> {creatingScenario ? "作成中" : "作成"}
        </button>
        <button type="button" disabled={creatingScenario} onclick={closeCreateScenarioModal}>キャンセル</button>
      </div>
    </div>
  </div>
{/if}

{#if descriptionModalOpen && activeScenario}
  <div class="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="desc-modal-heading">
    <button class="modal-scrim" type="button" aria-label="閉じる" onclick={() => (descriptionModalOpen = false)}></button>
    <div class="picker-modal description-modal">
      <div class="panel-header compact">
        <h3 id="desc-modal-heading">{activeScenario.name || activeScenario.id} - 説明</h3>
        <button class="icon-button" type="button" title="閉じる" onclick={() => (descriptionModalOpen = false)}>
          <X size={18} aria-hidden="true" />
        </button>
      </div>
      <div class="description-modal-body markdown-body">
        {@html renderMarkdown(activeScenario.description || "説明文はありません。")}
      </div>
    </div>
  </div>
{/if}

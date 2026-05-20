<script>
  import { ChevronLeft, ChevronRight } from "lucide-svelte";
  import {
    createPersona,
    getPersona,
    getProfile,
    listPersonas,
    listProfiles,
    updatePersona,
    updateProfile
  } from "./api.js";
  import { profileDataToPatch, profilePatchToPayload } from "./sessionPicker.js";
  import {
    getDefaultRpProfileId,
    getDefaultStateProfileId,
    roleplayProfiles,
    setDefaultRpProfileId,
    setDefaultStateProfileId,
    stateProfiles
  } from "./sessionSelection.js";

  /** @type {any} store returned by createSessionPickerStore() */
  export let pickerState;
  /** @type {any} store returned by createSessionSelectionStore() */
  export let selection;

  let defaultRpProfileId = getDefaultRpProfileId();
  let defaultStateProfileId = getDefaultStateProfileId();

  // モーダルが開いたとき、使用中のアイテムをデフォルトで詳細表示する
  $: {
    const kind = $pickerState.kind;
    const editId = $pickerState.editId;
    if (kind && !editId) {
      if (kind === "persona" && $selection.selectedPersona) {
        openPersonaEdit($selection.selectedPersona);
      } else if (kind === "roleplay" && $selection.selectedRpProfile) {
        openProfileEdit($selection.selectedRpProfile);
      } else if (kind === "state" && $selection.selectedStateProfile) {
        openProfileEdit($selection.selectedStateProfile);
      }
    }
  }

  function close() {
    pickerState.close();
  }

  /** @param {string} id */
  function setAsDefaultProfile(id) {
    if ($pickerState.kind === "roleplay") {
      setDefaultRpProfileId(id);
      defaultRpProfileId = id;
    } else {
      setDefaultStateProfileId(id);
      defaultStateProfileId = id;
    }
  }

  /** @param {string} id */
  async function openPersonaEdit(id) {
    pickerState.startPersonaEdit(id);
    try {
      const res = await getPersona(id);
      pickerState.setContent(res.content || "");
    } catch (e) {
      pickerState.setError(e instanceof Error ? e.message : "読み込みに失敗しました");
    } finally {
      pickerState.setLoadingEdit(false);
    }
  }

  /** @param {string} id */
  async function openProfileEdit(id) {
    pickerState.startProfileEdit(id);
    try {
      const res = await getProfile(id);
      pickerState.setProfilePatch(profileDataToPatch(res.data || {}));
    } catch (e) {
      pickerState.setError(e instanceof Error ? e.message : "読み込みに失敗しました");
    } finally {
      pickerState.setLoadingEdit(false);
    }
  }

  async function savePersonaEdit() {
    if (!$pickerState.editId || $pickerState.saving) return;
    pickerState.setSaving(true);
    pickerState.setError("");
    try {
      await updatePersona($pickerState.editId, $pickerState.content);
      pickerState.markClean();
      const personas = await listPersonas();
      selection.setPersonas(personas.personas || []);
    } catch (e) {
      pickerState.setError(e instanceof Error ? e.message : "保存に失敗しました");
    } finally {
      pickerState.setSaving(false);
    }
  }

  async function saveProfileEdit() {
    if (!$pickerState.editId || !$pickerState.profilePatch || $pickerState.saving) return;
    pickerState.setSaving(true);
    pickerState.setError("");
    try {
      await updateProfile($pickerState.editId, profilePatchToPayload($pickerState.profilePatch));
      pickerState.markClean();
      const profiles = await listProfiles();
      selection.setProfiles(profiles.profiles || []);
    } catch (e) {
      pickerState.setError(e instanceof Error ? e.message : "保存に失敗しました");
    } finally {
      pickerState.setSaving(false);
    }
  }

  async function submitNewPersona() {
    const id = $pickerState.newPersonaId.trim();
    const name = $pickerState.newPersonaName.trim();
    if (!id || !name) {
      pickerState.setNewPersonaError("IDと名前は必須です");
      return;
    }
    pickerState.setNewPersonaCreating(true);
    pickerState.setNewPersonaError("");
    try {
      await createPersona(id, name);
      const personas = await listPersonas();
      selection.setPersonas(personas.personas || []);
      pickerState.clearNewPersonaForm();
      await openPersonaEdit(id);
    } catch (e) {
      pickerState.setNewPersonaError(e instanceof Error ? e.message : "作成に失敗しました");
    } finally {
      pickerState.setNewPersonaCreating(false);
    }
  }

  /** @param {string} id */
  function choosePersona(id) {
    selection.choosePersona(id);
    close();
  }

  /** @param {string} id */
  function chooseRpProfile(id) {
    selection.chooseRpProfile(id);
    close();
  }

  /** @param {string} id */
  function chooseStateProfile(id) {
    selection.chooseStateProfile(id);
    close();
  }
</script>

<div class="modal-backdrop">
  <button class="modal-scrim" type="button" aria-label="閉じる" onclick={close}></button>
  <div
    class="picker-modal split-modal"
    role="dialog"
    aria-modal="true"
    aria-labelledby="picker-heading"
    tabindex="-1"
  >
    <div class="panel-header compact">
      <h3 id="picker-heading">
        {$pickerState.kind === "persona" ? "Persona" : $pickerState.kind === "roleplay" ? "GM profile" : "State profile"}
      </h3>
      <button class="icon-button" type="button" title="閉じる" onclick={close}>×</button>
    </div>

    <div class="picker-split">
      <!-- 左: 一覧 -->
      <div class="picker-split-list">
        {#if $pickerState.kind === "persona"}
          <ul class="picker-list">
            {#each $selection.personas as persona}
              <li>
                <button
                  class:selected={persona.id === $pickerState.editId}
                  class:in-use={persona.id === $selection.selectedPersona}
                  type="button"
                  onclick={() => openPersonaEdit(persona.id)}
                >
                  <strong>{persona.name || persona.id}</strong>
                  <span>{persona.id}{persona.id === $selection.selectedPersona ? " ✓使用中" : ""}</span>
                </button>
              </li>
            {/each}
          </ul>
          <div class="picker-list-footer">
            {#if $pickerState.creatingPersona}
              <div class="new-persona-form">
                <input
                  type="text"
                  placeholder="persona_id (英小文字_)"
                  value={$pickerState.newPersonaId}
                  oninput={(e) => pickerState.setNewPersonaId(e.currentTarget.value)}
                />
                <input
                  type="text"
                  placeholder="表示名"
                  value={$pickerState.newPersonaName}
                  oninput={(e) => pickerState.setNewPersonaName(e.currentTarget.value)}
                />
                {#if $pickerState.newPersonaError}
                  <span class="picker-error">{$pickerState.newPersonaError}</span>
                {/if}
                <div class="new-persona-actions">
                  <button type="button" disabled={$pickerState.newPersonaCreating} onclick={() => void submitNewPersona()}>
                    {$pickerState.newPersonaCreating ? "作成中..." : "作成"}
                  </button>
                  <button type="button" onclick={() => pickerState.setCreatingPersona(false)}>キャンセル</button>
                </div>
              </div>
            {:else}
              <button type="button" class="new-item-button" onclick={() => pickerState.setCreatingPersona(true)}>
                + 新規作成
              </button>
            {/if}
          </div>
        {:else if $pickerState.kind === "roleplay"}
          <ul class="picker-list">
            {#each roleplayProfiles($selection.profiles) as profile}
              <li>
                <button
                  class:selected={profile.id === $pickerState.editId}
                  class:in-use={profile.id === $selection.selectedRpProfile}
                  type="button"
                  onclick={() => openProfileEdit(profile.id)}
                >
                  <strong>{profile.id}{profile.id === defaultRpProfileId ? " ★" : ""}</strong>
                  <span>{profile.model}{profile.id === $selection.selectedRpProfile ? " ✓使用中" : ""}</span>
                </button>
              </li>
            {/each}
          </ul>
        {:else}
          <ul class="picker-list">
            {#each stateProfiles($selection.profiles) as profile}
              <li>
                <button
                  class:selected={profile.id === $pickerState.editId}
                  class:in-use={profile.id === $selection.selectedStateProfile}
                  type="button"
                  onclick={() => openProfileEdit(profile.id)}
                >
                  <strong>{profile.id}{profile.id === defaultStateProfileId ? " ★" : ""}</strong>
                  <span>{profile.kind} / {profile.model}{profile.id === $selection.selectedStateProfile ? " ✓使用中" : ""}</span>
                </button>
              </li>
            {/each}
          </ul>
        {/if}
      </div>

      <!-- 右: 編集エリア -->
      <div class="picker-split-edit">
        {#if $pickerState.loadingEdit}
          <p class="notice">読み込み中...</p>
        {:else if !$pickerState.editId}
          <p class="notice picker-hint">一覧から項目を選んでください。</p>
        {:else if $pickerState.kind === "persona"}
          <div class="picker-edit-header">
            <span class="picker-edit-id">{$pickerState.editId}</span>
          </div>
          <textarea
            class="picker-textarea"
            value={$pickerState.content}
            spellcheck="false"
            oninput={(e) => pickerState.updateContent(e.currentTarget.value)}
          ></textarea>
          {#if $pickerState.error}
            <span class="picker-error">{$pickerState.error}</span>
          {/if}
          <div class="picker-actions">
            <button type="button" class="use-button" onclick={() => choosePersona($pickerState.editId)}>
              このペルソナを使用
            </button>
            <button
              type="button"
              class="primary-button"
              disabled={$pickerState.saving || !$pickerState.dirty}
              onclick={() => void savePersonaEdit()}
            >
              {$pickerState.saving ? "保存中..." : "変更を保存"}
            </button>
          </div>
        {:else}
          <!-- Profile edit form -->
          {#if $pickerState.error}
            <span class="picker-error">{$pickerState.error}</span>
          {/if}
          {#if $pickerState.profilePatch}
            <div class="picker-edit-header">
              <span class="picker-edit-id">{$pickerState.editId}</span>
              <button
                type="button"
                class="default-star-button"
                class:active={$pickerState.kind === "roleplay" ? $pickerState.editId === defaultRpProfileId : $pickerState.editId === defaultStateProfileId}
                title={$pickerState.kind === "roleplay"
                  ? $pickerState.editId === defaultRpProfileId ? "デフォルト解除" : "デフォルトに設定"
                  : $pickerState.editId === defaultStateProfileId ? "デフォルト解除" : "デフォルトに設定"}
                onclick={() => setAsDefaultProfile($pickerState.editId)}
              >★</button>
            </div>
            <div class="profile-edit-form">
              <label>
                <span>Model</span>
                <input
                  type="text"
                  value={$pickerState.profilePatch.model}
                  oninput={(e) => pickerState.updateProfilePatch("model", e.currentTarget.value)}
                />
              </label>
              <label>
                <span>Temperature</span>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="2"
                  value={$pickerState.profilePatch.temperature}
                  oninput={(e) => pickerState.updateProfilePatch("temperature", e.currentTarget.value)}
                />
              </label>
              <label>
                <span>Top P</span>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="1"
                  value={$pickerState.profilePatch.top_p}
                  oninput={(e) => pickerState.updateProfilePatch("top_p", e.currentTarget.value)}
                />
              </label>
              <label>
                <span>Top K</span>
                <input
                  type="number"
                  step="1"
                  min="1"
                  value={$pickerState.profilePatch.top_k}
                  oninput={(e) => pickerState.updateProfilePatch("top_k", e.currentTarget.value)}
                />
              </label>
              <label>
                <span>Context Size</span>
                <input
                  type="number"
                  step="1"
                  min="1"
                  value={$pickerState.profilePatch.context_size}
                  oninput={(e) => pickerState.updateProfilePatch("context_size", e.currentTarget.value)}
                />
              </label>
              <label>
                <span>Max Tokens</span>
                <input
                  type="number"
                  step="1"
                  min="1"
                  value={$pickerState.profilePatch.max_tokens}
                  oninput={(e) => pickerState.updateProfilePatch("max_tokens", e.currentTarget.value)}
                />
              </label>
              <label>
                <span>Frequency Penalty</span>
                <input
                  type="number"
                  step="0.01"
                  min="-2"
                  max="2"
                  value={$pickerState.profilePatch.frequency_penalty}
                  oninput={(e) => pickerState.updateProfilePatch("frequency_penalty", e.currentTarget.value)}
                />
              </label>
              <label>
                <span>Presence Penalty</span>
                <input
                  type="number"
                  step="0.01"
                  min="-2"
                  max="2"
                  value={$pickerState.profilePatch.presence_penalty}
                  oninput={(e) => pickerState.updateProfilePatch("presence_penalty", e.currentTarget.value)}
                />
              </label>
              <label>
                <span>Repetition Penalty</span>
                <input
                  type="number"
                  step="0.01"
                  min="1"
                  max="2"
                  value={$pickerState.profilePatch.repetition_penalty}
                  oninput={(e) => pickerState.updateProfilePatch("repetition_penalty", e.currentTarget.value)}
                />
              </label>
              <label>
                <span>Reasoning Effort</span>
                <select
                  value={$pickerState.profilePatch.reasoning_effort}
                  onchange={(e) => pickerState.updateProfilePatch("reasoning_effort", e.currentTarget.value)}
                >
                  <option value="">— なし —</option>
                  <option value="low">low</option>
                  <option value="medium">medium</option>
                  <option value="high">high</option>
                </select>
              </label>
            </div>
          {/if}
          {#if $pickerState.editId && $pickerState.profilePatch}
            <div class="picker-actions">
              {#if $pickerState.kind === "roleplay"}
                <button type="button" class="use-button" onclick={() => chooseRpProfile($pickerState.editId)}>このプロファイルを使用</button>
              {:else}
                <button type="button" class="use-button" onclick={() => chooseStateProfile($pickerState.editId)}>このプロファイルを使用</button>
              {/if}
              <button
                type="button"
                class="primary-button"
                disabled={$pickerState.saving || !$pickerState.dirty}
                onclick={() => void saveProfileEdit()}
              >
                {$pickerState.saving ? "保存中..." : "変更を保存"}
              </button>
            </div>
          {/if}
        {/if}
      </div>
    </div>
  </div>
</div>

<script>
  import { ChevronLeft, ChevronRight } from "lucide-svelte";
  import { t, translateNow } from "./i18n.js";
  import {
    createPersona,
    getPersona,
    getProfile,
    listPersonas,
    listProfiles,
    testProfile,
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

  /** @type {{
   *   pickerState: any,
   *   selection: any,
   *   onChooseRpProfile?: ((id: string) => void) | null,
   *   onChooseStateProfile?: ((id: string) => void) | null,
   * }} */
  let {
    pickerState,
    selection,
    onChooseRpProfile = null,
    onChooseStateProfile = null
  } = $props();

  let defaultRpProfileId = $state(getDefaultRpProfileId());
  let defaultStateProfileId = $state(getDefaultStateProfileId());
  let profileTestRunning = $state(false);
  /** @type {Record<string, any> | null} */
  let profileTestResult = $state(null);
  let profileTestError = $state("");

  // モーダルが開いたとき、使用中のアイテムをデフォルトで詳細表示する
  $effect(() => {
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
  });

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
      pickerState.setError(e instanceof Error ? e.message : translateNow("picker.loadError"));
    } finally {
      pickerState.setLoadingEdit(false);
    }
  }

  /** @param {string} id */
  async function openProfileEdit(id) {
    pickerState.startProfileEdit(id);
    profileTestResult = null;
    profileTestError = "";
    try {
      const res = await getProfile(id);
      pickerState.setProfilePatch(profileDataToPatch(res.data || {}));
    } catch (e) {
      pickerState.setError(e instanceof Error ? e.message : translateNow("picker.loadError"));
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
      pickerState.setError(e instanceof Error ? e.message : translateNow("picker.saveError"));
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
      pickerState.setError(e instanceof Error ? e.message : translateNow("picker.saveError"));
    } finally {
      pickerState.setSaving(false);
    }
  }

  async function runProfileTest() {
    if (!$pickerState.editId || !$pickerState.profilePatch || profileTestRunning) return;
    profileTestRunning = true;
    profileTestResult = null;
    profileTestError = "";
    try {
      profileTestResult = await testProfile($pickerState.editId, profilePatchToPayload($pickerState.profilePatch));
    } catch (e) {
      profileTestError = e instanceof Error ? e.message : translateNow("picker.loadError");
    } finally {
      profileTestRunning = false;
    }
  }

  function profileConfigWarning() {
    const patch = $pickerState.profilePatch;
    if (!patch) return "";
    const contextSize = Number(patch.context_size);
    const maxTokens = Number(patch.max_tokens);
    if (!Number.isFinite(contextSize) || contextSize <= 0) {
      return "Context Size が未設定または不正です。Prompt 使用量の警告が正しく出ません。";
    }
    if (Number.isFinite(maxTokens) && maxTokens > 0) {
      if (maxTokens >= contextSize) return "Max Tokens が Context Size 以上です。応答前に context を使い切る可能性があります。";
      if (maxTokens > contextSize * 0.5) return "Max Tokens が Context Size の半分を超えています。長いPromptでは超過しやすくなります。";
    }
    if (contextSize < 4096) return "Context Size がかなり小さいため、長いセッションでは履歴やRAGが入りにくくなります。";
    return "";
  }

  async function submitNewPersona() {
    const id = $pickerState.newPersonaId.trim();
    const name = $pickerState.newPersonaName.trim();
    if (!id || !name) {
      pickerState.setNewPersonaError(translateNow("picker.idNameRequired"));
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
      pickerState.setNewPersonaError(e instanceof Error ? e.message : translateNow("picker.createError"));
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
    onChooseRpProfile?.(id);
    close();
  }

  /** @param {string} id */
  function chooseStateProfile(id) {
    selection.chooseStateProfile(id);
    onChooseStateProfile?.(id);
    close();
  }
</script>

<div class="modal-backdrop">
  <button class="modal-scrim" type="button" aria-label={$t("common.close")} onclick={close}></button>
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
      <button class="icon-button" type="button" title={$t("common.close")} onclick={close}>×</button>
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
                  <span>{persona.id}{persona.id === $selection.selectedPersona ? " " + $t("picker.inUse") : ""}</span>
                </button>
              </li>
            {/each}
          </ul>
          <div class="picker-list-footer">
            {#if $pickerState.creatingPersona}
              <div class="new-persona-form">
                <input
                  type="text"
                  placeholder={$t("picker.personaIdPlaceholder")}
                  value={$pickerState.newPersonaId}
                  oninput={(e) => pickerState.setNewPersonaId(e.currentTarget.value)}
                />
                <input
                  type="text"
                  placeholder={$t("picker.displayName")}
                  value={$pickerState.newPersonaName}
                  oninput={(e) => pickerState.setNewPersonaName(e.currentTarget.value)}
                />
                {#if $pickerState.newPersonaError}
                  <span class="picker-error">{$pickerState.newPersonaError}</span>
                {/if}
                <div class="new-persona-actions">
                  <button type="button" disabled={$pickerState.newPersonaCreating} onclick={() => void submitNewPersona()}>
                    {$pickerState.newPersonaCreating ? $t("picker.creating") : $t("common.create")}
                  </button>
                  <button type="button" onclick={() => pickerState.setCreatingPersona(false)}>{$t("common.cancel")}</button>
                </div>
              </div>
            {:else}
              <button type="button" class="new-item-button" onclick={() => pickerState.setCreatingPersona(true)}>
                {$t("picker.newCreate")}
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
                  <span>{profile.model}{profile.id === $selection.selectedRpProfile ? " " + $t("picker.inUse") : ""}</span>
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
                  <span>{profile.kind} / {profile.model}{profile.id === $selection.selectedStateProfile ? " " + $t("picker.inUse") : ""}</span>
                </button>
              </li>
            {/each}
          </ul>
        {/if}
      </div>

      <!-- 右: 編集エリア -->
      <div class="picker-split-edit">
        {#if $pickerState.loadingEdit}
          <p class="notice">{$t("picker.loading")}</p>
        {:else if !$pickerState.editId}
          <p class="notice picker-hint">{$t("picker.selectHint")}</p>
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
              {$t("picker.usePersona")}
            </button>
            <button
              type="button"
              class="primary-button"
              disabled={$pickerState.saving || !$pickerState.dirty}
              onclick={() => void savePersonaEdit()}
            >
              {$pickerState.saving ? $t("picker.saving") : $t("picker.saveChanges")}
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
                  ? $pickerState.editId === defaultRpProfileId ? $t("picker.unsetDefault") : $t("picker.setDefault")
                  : $pickerState.editId === defaultStateProfileId ? $t("picker.unsetDefault") : $t("picker.setDefault")}
                onclick={() => setAsDefaultProfile($pickerState.editId)}
              >★</button>
            </div>
            {#if profileConfigWarning()}
              <p class="picker-error">{profileConfigWarning()}</p>
            {/if}
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
                  <option value="">{$t("picker.noValue")}</option>
                  <option value="low">low</option>
                  <option value="medium">medium</option>
                  <option value="high">high</option>
                </select>
              </label>
            </div>
          {/if}
          {#if $pickerState.editId && $pickerState.profilePatch}
            <div class="profile-test-panel">
              <button type="button" disabled={profileTestRunning} onclick={() => void runProfileTest()}>
                {profileTestRunning ? "疎通確認中" : "疎通確認"}
              </button>
              {#if $pickerState.dirty}
                <span class="picker-hint">未保存変更を含めて疎通確認します。</span>
              {/if}
              {#if profileTestResult}
                <dl class="info-list compact-list">
                  <div><dt>Result</dt><dd>OK</dd></div>
                  <div><dt>Model</dt><dd>{profileTestResult.model || "—"}</dd></div>
                  <div><dt>Elapsed</dt><dd>{profileTestResult.elapsed_ms ?? "—"} ms</dd></div>
                  {#if profileTestResult.finish_reason}
                    <div><dt>Finish</dt><dd>{profileTestResult.finish_reason}</dd></div>
                  {/if}
                  {#if profileTestResult.usage}
                    <div><dt>Usage</dt><dd>{JSON.stringify(profileTestResult.usage)}</dd></div>
                  {/if}
                </dl>
              {/if}
              {#if profileTestError}
                <span class="picker-error">{profileTestError}</span>
              {/if}
            </div>
            <div class="picker-actions">
              {#if $pickerState.kind === "roleplay"}
                <button type="button" class="use-button" onclick={() => chooseRpProfile($pickerState.editId)}>{$t("picker.useProfile")}</button>
              {:else}
                <button type="button" class="use-button" onclick={() => chooseStateProfile($pickerState.editId)}>{$t("picker.useProfile")}</button>
              {/if}
              <button
                type="button"
                class="primary-button"
                disabled={$pickerState.saving || !$pickerState.dirty}
                onclick={() => void saveProfileEdit()}
              >
                {$pickerState.saving ? $t("picker.saving") : $t("picker.saveChanges")}
              </button>
            </div>
          {/if}
        {/if}
      </div>
    </div>
  </div>
</div>

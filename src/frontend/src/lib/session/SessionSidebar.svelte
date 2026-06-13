<script>
  import { PanelLeftClose } from "lucide-svelte";
  import { personaName, profileModel } from "../sessionSelection.js";
  import { t } from "../i18n.js";

  /** @type {{
   *   layout: any,
   *   selection: any,
   *   scenarioId?: string,
   *   currentSessionId?: string,
   *   startings?: Array<Record<string, any>>,
   *   selectedStartingId?: string,
   *   loading?: boolean,
   *   openPicker?: (kind: "persona" | "roleplay" | "state") => void,
   *   createSelectedSession?: () => Promise<void>,
   * }} */
  let {
    layout,
    selection,
    scenarioId = "",
    currentSessionId = "",
    startings = [],
    selectedStartingId = $bindable(""),
    loading = false,
    openPicker = (_kind) => {},
    createSelectedSession = async () => {}
  } = $props();
</script>

  <aside class="session-side" aria-labelledby="session-side-heading">
    <div class="brand-block">
      <div>
        <p class="eyebrow">Obsidian-first RP</p>
        <h1 id="session-side-heading">Locus RP</h1>
      </div>
      <button class="icon-button" type="button" title={$t("session.closeSideCol")} onclick={() => layout.setSideOpen(false)}>
        <PanelLeftClose size={18} aria-hidden="true" />
      </button>
    </div>

    <section class="control-group" aria-labelledby="profile-heading">
      <h2 id="profile-heading">Profiles</h2>
      <div class="setting-stack">
        <button class="setting-card setting-card-button" type="button" onclick={() => openPicker("persona")}>
          <div class="setting-card-head">
            <span>Persona</span>
            <span class="card-action-label">{$t("session.change")}</span>
          </div>
          <strong>{personaName($selection, $selection.selectedPersona)}</strong>
          <small>{scenarioId || $t("session.noScenarioId")}</small>
        </button>
        <button class="setting-card setting-card-button" type="button" onclick={() => openPicker("roleplay")}>
          <div class="setting-card-head">
            <span>GM profile</span>
            <span class="card-action-label">{$t("session.change")}</span>
          </div>
          <strong>{$selection.selectedRpProfile}</strong>
          <small>{profileModel($selection, $selection.selectedRpProfile)}</small>
        </button>
        <button class="setting-card setting-card-button" type="button" onclick={() => openPicker("state")}>
          <div class="setting-card-head">
            <span>State profile</span>
            <span class="card-action-label">{$t("session.change")}</span>
          </div>
          <strong>{$selection.selectedStateProfile}</strong>
          <small>{profileModel($selection, $selection.selectedStateProfile)}</small>
        </button>
      </div>
    </section>

    {#if !currentSessionId}
      <section class="control-group" aria-labelledby="starting-heading">
        <h2 id="starting-heading">Starting</h2>
        {#if startings.length}
          <label class="setting-card">
            <span>{$t("session.startSituation")}</span>
            <select class="compact-input" bind:value={selectedStartingId}>
              {#each startings as starting}
                <option value={starting.id}>{starting.name || starting.id}</option>
              {/each}
            </select>
            <small>{startings.find((/** @type {any} */ s) => s.id === selectedStartingId)?.name || selectedStartingId}</small>
          </label>
        {:else}
          <p class="notice">{$t("session.noStarting")}</p>
        {/if}
      </section>
    {/if}

    {#if !currentSessionId}
      <button class="primary-action" type="button" disabled={loading} onclick={() => void createSelectedSession()}>
        {$t("session.selectAndStart")}
      </button>
    {/if}

  </aside>

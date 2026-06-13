<script>
  import { ChevronDown } from "lucide-svelte";
  import { onMount } from "svelte";
  import FrontPage from "./pages/FrontPage.svelte";
  import ScenarioEditPage from "./pages/ScenarioEditPage.svelte";
  import SessionPage from "./pages/SessionPage.svelte";
  import { navigate, route, ROUTE_NAMES } from "./lib/router.js";
  import { getHealth } from "./lib/api.js";
  import { locale, localeOptions, setLocale, t } from "./lib/i18n.js";

  const navigation = {
    openHome: () => navigate("/"),
    /**
     * @param {string} scenarioId
     * @param {string} [sessionId]
     */
    openSession: (scenarioId, sessionId) => navigate("/session", { scenario: scenarioId, session: sessionId }),
    /**
     * @param {string} scenarioId
     * @param {string} [sourcePath]
     */
    openScenarioEdit: (scenarioId, sourcePath) => navigate("/scenario", { scenario: scenarioId, mode: "edit", source: sourcePath })
  };

  /**
   * @typedef {{ accessible: boolean, root: string, dirs: Record<string, boolean> }} VaultStatus
   * @typedef {{ backend: "ok" | "error", vault?: VaultStatus } | null} HealthStatus
   */

  let health = $state(/** @type {HealthStatus} */ (null));
  let healthLoading = $state(true);
  let mobileSidebarOpen = $state(false);

  const VAULT_DIR_LABELS = {
    "rp/scenarios": "scenarios",
    "rp/personas": "personas",
    "rp/profiles": "profiles",
  };

  async function refreshHealth() {
    try {
      health = await getHealth();
    } catch {
      health = { backend: "error" };
    } finally {
      healthLoading = false;
    }
  }

  onMount(() => {
    void refreshHealth();
  });
</script>

{#if $route.name === ROUTE_NAMES.session}
  <SessionPage route={$route} onNavigate={navigation} />
{:else}
  <main class="app-shell">
    <aside class:mobile-open={mobileSidebarOpen} class="sidebar">
      <button
        class="mobile-sidebar-toggle"
        type="button"
        aria-expanded={mobileSidebarOpen}
        aria-controls="mobile-sidebar-panel"
        onclick={() => (mobileSidebarOpen = !mobileSidebarOpen)}
      >
        <span>
          <span class="eyebrow">Obsidian-first RP</span>
          <strong>Locus RP</strong>
        </span>
        <ChevronDown size={18} aria-hidden="true" />
      </button>

      {#if mobileSidebarOpen}
        <button
          class="mobile-sidebar-scrim"
          type="button"
          aria-label={$t("app.closeSidebar")}
          onclick={() => (mobileSidebarOpen = false)}
        ></button>
      {/if}

      <div id="mobile-sidebar-panel" class="sidebar-content">
        <p class="eyebrow">Obsidian-first RP</p>
        <h1>Locus RP</h1>
        <p>{$t("app.tagline")}</p>

        <div class="sidebar-status">
          <p class="eyebrow">System Status</p>
          {#if healthLoading}
            <ul class="status-list">
              <li class="status-item status-loading"><span class="status-dot"></span>{$t("app.statusChecking")}</li>
            </ul>
          {:else}
            <ul class="status-list">
              <li class="status-item" class:status-ok={health?.backend === "ok"} class:status-ng={health?.backend !== "ok"}>
                <span class="status-dot"></span>Backend
              </li>
              {#if health?.vault}
                <li class="status-item" class:status-ok={health.vault.accessible} class:status-ng={!health.vault.accessible}>
                  <span class="status-dot"></span>Vault
                </li>
                {#each Object.entries(VAULT_DIR_LABELS) as [key, label]}
                  <li class="status-item status-sub" class:status-ok={health.vault.dirs[key]} class:status-ng={!health.vault.dirs[key]}>
                    <span class="status-dot"></span>{label}
                  </li>
                {/each}
              {/if}
            </ul>
            <button class="status-refresh" type="button" onclick={() => void refreshHealth()}>{$t("app.refresh")}</button>
          {/if}
          <label class="language-select">
            <span>{$t("app.language")}</span>
            <select class="compact-input" value={$locale} onchange={(event) => setLocale(event.currentTarget.value)}>
              {#each localeOptions as option}
                <option value={option.code}>{option.label}</option>
              {/each}
            </select>
          </label>
        </div>
      </div>
    </aside>

    <section class="workspace" class:scenario-edit={$route.name === ROUTE_NAMES.scenario} aria-labelledby="workspace-heading">
      {#if $route.name === ROUTE_NAMES.front}
      <FrontPage onNavigate={navigation} />
      {:else if $route.name === ROUTE_NAMES.scenario}
      <ScenarioEditPage route={$route} onNavigate={navigation} />
      {:else}
      <div class="toolbar">
        <div>
          <p class="eyebrow">Not Found</p>
          <h2 id="workspace-heading">Route Not Found</h2>
        </div>
        <button type="button" onclick={navigation.openHome}>Home</button>
      </div>
      <p class="notice">{$t("app.notFound.notice")}</p>
      {/if}
    </section>
  </main>
{/if}

<script>
  import { ChevronDown } from "lucide-svelte";
  import { onMount } from "svelte";
  import FrontPage from "./pages/FrontPage.svelte";
  import ScenarioEditPage from "./pages/ScenarioEditPage.svelte";
  import SessionPage from "./pages/SessionPage.svelte";
  import { navigate, route, ROUTE_NAMES } from "./lib/router.js";
  import { getHealth } from "./lib/api.js";

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

  /** @type {HealthStatus} */
  let health = null;
  let healthLoading = true;
  let mobileSidebarOpen = false;

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
          aria-label="サイドビューを閉じる"
          onclick={() => (mobileSidebarOpen = false)}
        ></button>
      {/if}

      <div id="mobile-sidebar-panel" class="sidebar-content">
        <p class="eyebrow">Obsidian-first RP</p>
        <h1>Locus RP</h1>
        <p>あなたの物語を、Obsidianから。</p>

        <div class="sidebar-status">
          <p class="eyebrow">System Status</p>
          {#if healthLoading}
            <ul class="status-list">
              <li class="status-item status-loading"><span class="status-dot"></span>確認中…</li>
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
            <button class="status-refresh" type="button" onclick={() => void refreshHealth()}>再確認</button>
          {/if}
        </div>
      </div>
    </aside>

    <section class="workspace" aria-labelledby="workspace-heading">
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
      <p class="notice">この URL に対応する画面はまだありません。</p>
      {/if}
    </section>
  </main>
{/if}

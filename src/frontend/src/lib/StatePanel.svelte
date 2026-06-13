<script>
  import { getScenarioStateTemplate } from "./api.js";
  import { buildRenderedHtml } from "./stateTemplate.js";

  /** The prop is still named `state` for callers; the local alias avoids
   * clashing with the $state rune inside this component. */
  /** @type {{ state?: Record<string, any> | null, scenarioId?: string, stateJsonStr?: string }} */
  let { state: stateData = null, scenarioId = "", stateJsonStr = "" } = $props();

  let hasTemplate = $state(false);
  let templateHtml = $state("");
  let templateCss = $state("");
  let errorFallback = $state(false);

  /** @type {HTMLElement | undefined} */
  let shadowContainer = $state();

  $effect(() => {
    if (scenarioId) {
      void loadTemplate(scenarioId);
    }
  });

  $effect(() => {
    if (hasTemplate && !errorFallback && shadowContainer && stateData) {
      updateShadowDOM();
    }
  });

  /** @param {string} id */
  async function loadTemplate(id) {
    hasTemplate = false;
    errorFallback = false;
    try {
      const res = await getScenarioStateTemplate(id);
      if (res && res.has_template) {
        hasTemplate = true;
        templateHtml = res.html || "";
        templateCss = res.css || "";
      } else {
        hasTemplate = false;
      }
    } catch (e) {
      hasTemplate = false;
    }
  }

  function updateShadowDOM() {
    if (!shadowContainer) return;
    try {
      let shadowRoot = shadowContainer.shadowRoot;
      if (!shadowRoot) {
        shadowRoot = shadowContainer.attachShadow({ mode: "open" });
      }
      const renderedHtml = buildRenderedHtml(templateHtml, stateData || {});
      shadowRoot.innerHTML = `<style>${templateCss}</style>${renderedHtml}`;
    } catch (e) {
      console.error("Shadow DOM render error", e);
      errorFallback = true;
    }
  }
</script>

{#if !hasTemplate || errorFallback}
  <pre>{stateJsonStr}</pre>
{:else}
  <div bind:this={shadowContainer} class="state-template-container"></div>
{/if}

<style>
  .state-template-container {
    display: block;
    width: 100%;
  }
</style>

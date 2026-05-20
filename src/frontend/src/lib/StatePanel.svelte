<script>
  import { getScenarioStateTemplate } from "./api.js";
  import { buildRenderedHtml } from "./stateTemplate.js";

  /** @type {Record<string, any> | null} */
  export let state = null;
  /** @type {string} */
  export let scenarioId = "";
  /** @type {string} */
  export let stateJsonStr = "";

  let hasTemplate = false;
  let templateHtml = "";
  let templateCss = "";
  let errorFallback = false;

  /** @type {HTMLElement | undefined} */
  let shadowContainer;

  $: if (scenarioId) {
    void loadTemplate(scenarioId);
  }

  $: if (hasTemplate && !errorFallback && shadowContainer && state) {
    updateShadowDOM();
  }

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
      const renderedHtml = buildRenderedHtml(templateHtml, state || {});
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

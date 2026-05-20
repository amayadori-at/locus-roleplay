<script>
  import { Play } from "lucide-svelte";

  export let loadingPreviewChoices = false;
  export let loadingPromptPreview = false;
  export let promptPreviewError = "";
  /** @type {Record<string, any> | null} */
  export let promptPreview = null;
  /** @type {Array<Record<string, any>>} */
  export let sessions = [];
  /** @type {Array<Record<string, any>>} */
  export let personas = [];
  export let previewSessionId = "";
  export let previewPersonaId = "";
  export let previewProfileId = "";
  export let previewUserMessage = "";
  /** @type {() => Array<Record<string, any>>} */
  export let roleplayProfiles = () => [];
  export let runPromptPreview = () => {};

  function promptPreviewJson() {
    return JSON.stringify(promptPreview?.messages || [], null, 2);
  }
</script>

<section class="prompt-preview-panel" aria-labelledby="prompt-preview-heading">
  <div class="panel-header compact">
    <div>
      <p class="eyebrow">Preview</p>
      <h4 id="prompt-preview-heading">事前Prompt Preview</h4>
    </div>
    <button
      type="button"
      disabled={loadingPreviewChoices || loadingPromptPreview || !previewUserMessage.trim()}
      onclick={() => void runPromptPreview()}
    >
      <Play size={15} aria-hidden="true" /> {loadingPromptPreview ? "生成中" : "生成"}
    </button>
  </div>

  <div class="prompt-preview-controls">
    <label>
      <span>Session</span>
      <select class="compact-input" bind:value={previewSessionId} disabled={loadingPreviewChoices}>
        <option value="">セッションなし</option>
        {#each sessions as session}
          <option value={session.session_id}>
            {session.display_name || session.session_id}
          </option>
        {/each}
      </select>
    </label>

    {#if !previewSessionId}
      <label>
        <span>Persona</span>
        <select class="compact-input" bind:value={previewPersonaId} disabled={loadingPreviewChoices}>
          {#each personas as persona}
            <option value={persona.id}>{persona.name || persona.id}</option>
          {/each}
        </select>
      </label>
      <label>
        <span>Profile</span>
        <select class="compact-input" bind:value={previewProfileId} disabled={loadingPreviewChoices}>
          {#each roleplayProfiles() as profile}
            <option value={profile.id}>{profile.id} / {profile.model}</option>
          {/each}
        </select>
      </label>
    {/if}

    <label class="preview-message-field">
      <span>User message</span>
      <textarea class="compact-input" rows="3" bind:value={previewUserMessage}></textarea>
    </label>
  </div>

  {#if promptPreviewError}
    <p class="notice error-notice">{promptPreviewError}</p>
  {/if}

  {#if promptPreview}
    <div class="prompt-preview-output">
      <div class="prompt-graph-meta">
        <span>graph: {promptPreview.graph?.id}</span>
        <span>persona: {promptPreview.persona_id}</span>
        <span>profile: {promptPreview.profile?.id}</span>
        <span>messages: {promptPreview.message_count}</span>
        <span>tokens: {promptPreview.token_usage?.prompt_tokens ?? 0}</span>
      </div>

      <ul class="prompt-expansion-list" aria-label="Prompt node expansions">
        {#each promptPreview.expansions || [] as expansion}
          <li class:skipped={!expansion.included}>
            <strong>{expansion.node_id}</strong>
            <span>{expansion.role}</span>
            <span>{expansion.included ? `${expansion.content_tokens || 0} tokens` : expansion.skipped_reason}</span>
          </li>
        {/each}
      </ul>

      <pre class="prompt-preview-json">{promptPreviewJson()}</pre>
    </div>
  {:else}
    <p class="notice">
      モデル呼び出しなしで、現在のGraphと入力条件から送信予定messagesを事前確認できます。このPreviewは保存されません。
    </p>
  {/if}
</section>

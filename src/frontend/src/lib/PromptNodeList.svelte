<script>
  import { Plus } from "lucide-svelte";
  import { t } from "./i18n.js";
  import { nodeSubText, nodeTypeBadge, nodeTypeCssClass } from "./promptGraphEditor.js";

  /** @type {Array<Record<string, any>>} */
  export let nodes = [];
  export let selectedNodeId = "";
  export let draggedNodeId = "";
  export let dragTargetNodeId = "";
  export let dragDropAfter = false;
  /** @type {(nodeId: string) => void} */
  export let selectNode = () => {};
  /** @type {(nodeId: string, event: PointerEvent) => void} */
  export let startNodeDrag = () => {};
  /** @type {() => void} */
  export let addNode = () => {};

  /** @param {string} nodeId */
  function activateNode(nodeId) {
    selectNode(nodeId);
  }
</script>

<div class="node-list-pane">
  <div class="pane-header">
    <h4>Nodes ({nodes.length})</h4>
  </div>
  <div class="node-list">
    {#each nodes as node (node.id)}
      <div
        class="node-item"
        data-node-id={node.id}
        class:selected={selectedNodeId === node.id}
        class:dragging={draggedNodeId === node.id}
        class:drop-before={dragTargetNodeId === node.id && !dragDropAfter}
        class:drop-after={dragTargetNodeId === node.id && dragDropAfter}
        role="button"
        tabindex="0"
        onclick={() => activateNode(node.id)}
        onkeydown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            activateNode(node.id);
          }
        }}
      >
        <button
          class="drag-handle"
          type="button"
          tabindex="-1"
          title="Drag to reorder"
          onpointerdown={(event) => startNodeDrag(node.id, event)}
          onclick={(event) => event.stopPropagation()}
        >⋮⋮</button>
        <span class="order-badge">{node.order}</span>
        <span class="type-badge {nodeTypeCssClass(node.type)}">{nodeTypeBadge(node.type)}</span>
        <div class="node-info">
          <div class="node-id">{node.id}</div>
          <div class="node-sub">{nodeSubText(node)}</div>
        </div>
        <span class="req-dot" class:off={!node.required} title={node.required ? "必須ノード" : ""}></span>
      </div>
    {/each}
  </div>
  <div class="node-add-row">
    <button type="button" onclick={addNode}>
      <Plus size={13} aria-hidden="true" /> {$t("editor.addNode")}
    </button>
  </div>
</div>

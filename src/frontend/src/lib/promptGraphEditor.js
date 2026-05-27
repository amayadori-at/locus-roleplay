export const RAG_SOURCE_OPTIONS = ["memory", "lore", "characters"];
export const RAG_TYPE_BUDGET_KEYS = ["memory", "lore", "character"];
export const TYPE_SCOPED_FIELDS = ["path", "source", "limit", "budget_enabled", "token_budget", "keyword_token_budget", "token_budgets"];
export const DEFAULT_SESSION_LOG_TOKEN_BUDGET = 12000;

export const DEFAULT_RAG_NODE_FIELDS = Object.freeze({
  source: RAG_SOURCE_OPTIONS,
  limit: 6,
  token_budget: 6000,
  keyword_token_budget: 1200,
  token_budgets: Object.freeze({
    memory: 2400,
    lore: 2400,
    character: 1800
  })
});

/**
 * @param {unknown} value
 * @returns {number | undefined}
 */
export function parseOptionalNumber(value) {
  const trimmed = String(value ?? "").trim();
  if (!trimmed) return undefined;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? parsed : undefined;
}

/**
 * @param {Record<string, any>} node
 * @returns {Array<string>}
 */
export function normalizedRagSources(node) {
  const raw = Array.isArray(node?.source) ? node.source : DEFAULT_RAG_NODE_FIELDS.source;
  const values = raw.filter((item) => RAG_SOURCE_OPTIONS.includes(item));
  return values.length ? Array.from(new Set(values)) : [...DEFAULT_RAG_NODE_FIELDS.source];
}

/**
 * @param {Record<string, any>} node
 * @returns {Record<string, any>}
 */
export function withRagDefaults(node) {
  if (node.budget_enabled === false) {
    return {
      ...withoutBudgetFields(node),
      budget_enabled: false,
      source: Array.isArray(node.source) ? normalizedRagSources(node) : [...DEFAULT_RAG_NODE_FIELDS.source],
      limit: typeof node.limit === "number" && Number.isFinite(node.limit) ? node.limit : DEFAULT_RAG_NODE_FIELDS.limit
    };
  }
  const budgets = typeof node.token_budgets === "object" && node.token_budgets !== null && !Array.isArray(node.token_budgets)
    ? { ...DEFAULT_RAG_NODE_FIELDS.token_budgets, ...node.token_budgets }
    : { ...DEFAULT_RAG_NODE_FIELDS.token_budgets };
  return {
    ...node,
    source: Array.isArray(node.source) ? normalizedRagSources(node) : [...DEFAULT_RAG_NODE_FIELDS.source],
    limit: typeof node.limit === "number" && Number.isFinite(node.limit) ? node.limit : DEFAULT_RAG_NODE_FIELDS.limit,
    token_budget: typeof node.token_budget === "number" && Number.isFinite(node.token_budget)
      ? node.token_budget
      : DEFAULT_RAG_NODE_FIELDS.token_budget,
    keyword_token_budget: typeof node.keyword_token_budget === "number" && Number.isFinite(node.keyword_token_budget)
      ? node.keyword_token_budget
      : DEFAULT_RAG_NODE_FIELDS.keyword_token_budget,
    token_budgets: budgets
  };
}

/** @param {Record<string, any>} node */
export function withoutBudgetFields(node) {
  const next = { ...node };
  delete next.token_budget;
  delete next.keyword_token_budget;
  delete next.token_budgets;
  return next;
}

/** @param {Record<string, any>} node */
export function budgetEnabled(node) {
  return node.budget_enabled !== false;
}

/**
 * @param {Record<string, any>} node
 * @param {boolean} enabled
 */
export function setBudgetEnabled(node, enabled) {
  if (!enabled) {
    return { ...withoutBudgetFields(node), budget_enabled: false };
  }
  const next = { ...node, budget_enabled: true };
  if (node.type === "rag") {
    return withRagDefaults(next);
  }
  if (node.type === "session_log") {
    return {
      ...next,
      token_budget: typeof node.token_budget === "number" && Number.isFinite(node.token_budget)
        ? node.token_budget
        : DEFAULT_SESSION_LOG_TOKEN_BUDGET
    };
  }
  return next;
}

/**
 * @param {Record<string, any>} node
 * @param {string} source
 * @param {boolean} enabled
 * @returns {Record<string, any>}
 */
export function setRagSource(node, source, enabled) {
  if (!RAG_SOURCE_OPTIONS.includes(source)) return node;
  const current = normalizedRagSources(node);
  let next = enabled ? [...current, source] : current.filter((item) => item !== source);
  next = Array.from(new Set(next)).filter((item) => RAG_SOURCE_OPTIONS.includes(item));
  if (!next.length) {
    next = [source];
  }
  return { ...node, source: next };
}

/**
 * @param {Record<string, any>} node
 * @param {string} key
 * @param {number | undefined} value
 * @returns {Record<string, any>}
 */
export function setRagTypeBudget(node, key, value) {
  if (!RAG_TYPE_BUDGET_KEYS.includes(key)) return node;
  const current = typeof node.token_budgets === "object" && node.token_budgets !== null && !Array.isArray(node.token_budgets)
    ? { ...node.token_budgets }
    : {};
  if (typeof value === "number" && Number.isFinite(value)) {
    current[key] = value;
  } else {
    delete current[key];
  }
  return Object.keys(current).length ? { ...node, token_budgets: current } : withoutField(node, "token_budgets");
}

/**
 * @param {Record<string, any>} node
 * @param {string} field
 * @param {number | undefined} value
 * @returns {Record<string, any>}
 */
export function setOptionalNumberField(node, field, value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return { ...node, [field]: value };
  }
  return withoutField(node, field);
}

/**
 * @param {Record<string, any>} node
 * @param {string} field
 * @returns {Record<string, any>}
 */
export function withoutField(node, field) {
  const next = { ...node };
  delete next[field];
  return next;
}

/**
 * @param {Record<string, any>} node
 * @param {number} fallbackIndex
 */
export function sortableOrder(node, fallbackIndex) {
  const value = Number(node.order);
  return Number.isFinite(value) ? value : Number.POSITIVE_INFINITY + fallbackIndex;
}

/** @param {Array<Record<string, any>>} nodes */
export function sortPromptNodes(nodes) {
  return nodes
    .map((node, index) => ({ node, index }))
    .sort((left, right) => {
      const diff = sortableOrder(left.node, left.index) - sortableOrder(right.node, right.index);
      return diff || left.index - right.index;
    })
    .map((item) => item.node);
}

/**
 * @param {Array<Record<string, any>>} nodes
 * @returns {Array<Record<string, any>>}
 */
export function renumberPromptNodes(nodes) {
  return sortPromptNodes(nodes).map((node, index) => ({ ...node, order: (index + 1) * 10 }));
}

/**
 * @param {Array<Record<string, any>>} nodes
 * @returns {Array<Record<string, any>>}
 */
export function assignSequentialOrder(nodes) {
  return nodes.map((node, index) => ({ ...node, order: (index + 1) * 10 }));
}

/** @param {Record<string, any>} graph */
export function graphWithNormalizedOrder(graph) {
  return { ...graph, nodes: renumberPromptNodes(/** @type {Array<Record<string, any>>} */ (graph.nodes || [])) };
}

/** @param {Array<Record<string, any>>} nodes */
export function promptOrderDuplicateWarnings(nodes) {
  /** @type {Map<number, Array<string>>} */
  const grouped = new Map();
  for (const node of nodes) {
    const value = Number(node.order);
    if (!Number.isFinite(value)) continue;
    grouped.set(value, [...(grouped.get(value) || []), node.id || "(unnamed)"]);
  }
  return [...grouped.entries()]
    .filter(([, ids]) => ids.length > 1)
    .map(([order, ids]) => `order ${order} が重複しています: ${ids.join(", ")}。保存時に表示順で再採番されます。`);
}

/** @param {Array<Record<string, any>>} nodes */
export function promptNodeOrderSnapshot(nodes) {
  return nodes.map((node) => ({ id: node.id || "", order: node.order }));
}

/**
 * @param {Array<Record<string, any>>} nodes
 * @param {number} index
 * @param {"up" | "down"} direction
 * @returns {Array<Record<string, any>> | null}
 */
export function movePromptNode(nodes, index, direction) {
  const reordered = [...nodes];
  const nextIndex = direction === "up" ? index - 1 : index + 1;
  if (index < 0 || index >= reordered.length || nextIndex < 0 || nextIndex >= reordered.length) return null;
  [reordered[index], reordered[nextIndex]] = [reordered[nextIndex], reordered[index]];
  return assignSequentialOrder(reordered);
}

/**
 * @param {Array<Record<string, any>>} nodes
 * @param {string} sourceNodeId
 * @param {string} targetNodeId
 * @param {boolean} insertAfter
 * @returns {{ nodes: Array<Record<string, any>>, movedId: string, sourceIndex: number, targetIndex: number, insertIndex: number } | null}
 */
export function reorderPromptNodeByDrop(nodes, sourceNodeId, targetNodeId, insertAfter) {
  if (!sourceNodeId || !targetNodeId || sourceNodeId === targetNodeId) return null;
  const nextNodes = [...nodes];
  const sourceIndex = nextNodes.findIndex((node) => node.id === sourceNodeId);
  const targetIndex = nextNodes.findIndex((node) => node.id === targetNodeId);
  if (sourceIndex < 0 || targetIndex < 0) return null;
  const [moved] = nextNodes.splice(sourceIndex, 1);
  let insertIndex = targetIndex + (insertAfter ? 1 : 0);
  if (sourceIndex < insertIndex) {
    insertIndex -= 1;
  }
  insertIndex = Math.max(0, Math.min(insertIndex, nextNodes.length));
  if (sourceIndex === insertIndex) return null;
  nextNodes.splice(insertIndex, 0, moved);
  return {
    nodes: assignSequentialOrder(nextNodes),
    movedId: moved.id,
    sourceIndex,
    targetIndex,
    insertIndex
  };
}

/**
 * @param {Record<string, any>} graph
 * @param {Array<Record<string, any>>} nodes
 * @param {number} index
 * @returns {Record<string, any> | null}
 */
export function deletePromptNodeFromGraph(graph, nodes, index) {
  if (index < 0 || index >= nodes.length) return null;
  const nextNodes = [...nodes];
  const removedId = nextNodes[index]?.id;
  nextNodes.splice(index, 1);
  /** @type {Record<string, any>} */
  const nextGraph = { ...graph, nodes: nextNodes };
  if (Array.isArray(graph.edges)) {
    nextGraph.edges = graph.edges.filter((edge) => edge.source !== removedId && edge.target !== removedId);
  }
  return nextGraph;
}

/**
 * @param {Record<string, any>} graph
 * @param {Array<Record<string, any>>} nodes
 * @param {number} index
 * @returns {{ graph: Record<string, any>, id: string } | null}
 */
export function duplicatePromptNodeInGraph(graph, nodes, index) {
  const source = nodes[index];
  if (!source) return null;
  const maxOrder = nodes.reduce((max, node) => Math.max(max, node.order ?? 0), 0);
  let uniqueId = `${source.id}_copy`;
  let suffix = 2;
  while (nodes.some((node) => node.id === uniqueId)) {
    uniqueId = `${source.id}_copy${suffix}`;
    suffix++;
  }
  const duplicated = { ...source, id: uniqueId, order: maxOrder + 10 };
  return { graph: { ...graph, nodes: [...nodes, duplicated] }, id: uniqueId };
}

/**
 * @param {Record<string, any>} graph
 * @param {Array<Record<string, any>>} nodes
 * @param {number} index
 * @param {string} id
 * @returns {Record<string, any> | null}
 */
export function renamePromptNodeInGraph(graph, nodes, index, id) {
  if (index < 0 || index >= nodes.length) return null;
  const updated = [...nodes];
  const oldId = updated[index]?.id;
  updated[index] = { ...updated[index], id };
  /** @type {Record<string, any>} */
  const nextGraph = { ...graph, nodes: updated };
  if (Array.isArray(graph.edges)) {
    nextGraph.edges = graph.edges.map((edge) => ({
      ...edge,
      source: edge.source === oldId ? id : edge.source,
      target: edge.target === oldId ? id : edge.target
    }));
  }
  return nextGraph;
}

/** @param {Array<Record<string, any>>} graphNodes */
export function buildPromptFlowNodes(graphNodes) {
  const nodes = graphNodes.map((node, index) => ({
    id: node.id,
    type: index === 0 ? "input" : "default",
    data: {
      label: `${node.order} ${node.id}\n${node.type} / ${node.role}`
    },
    position: { x: index * 220, y: node.condition ? 110 : 40 },
    class: `prompt-flow-node prompt-flow-${node.type}${node.required ? " required" : ""}`
  }));
  if (nodes.length) {
    nodes.push({
      id: "final_prompt",
      type: "output",
      data: { label: "⬛ final prompt" },
      position: { x: nodes.length * 220, y: 40 },
      class: "prompt-flow-node prompt-flow-final"
    });
  }
  return nodes;
}

/**
 * @param {Array<Record<string, any>>} graphNodes
 * @param {Array<Record<string, any>>} graphEdges
 * @param {string} activeNodeId
 */
export function buildPromptFlowEdges(graphNodes, graphEdges, activeNodeId) {
  if (graphEdges.length) {
    return graphEdges.map((edge) => ({
      id: `${edge.source}-${edge.target}`,
      source: edge.source,
      target: edge.target,
      animated: edge.source === activeNodeId
    }));
  }
  const ids = graphNodes.map((node) => node.id);
  if (ids.length) {
    ids.push("final_prompt");
  }
  return ids.slice(0, -1).map((source, index) => ({
    id: `${source}-${ids[index + 1]}`,
    source,
    target: ids[index + 1],
    animated: source === activeNodeId
  }));
}

/** @param {string} type */
export function defaultRoleForType(type) {
  if (type === "current_user_message") return "user";
  if (type === "session_log") return "messages";
  return "system";
}

/**
 * @param {Record<string, any>} node
 * @param {string} nextType
 * @param {string} fallbackPath
 * @returns {Record<string, any>}
 */
export function normalizeNodeForType(node, nextType, fallbackPath = "scenario.md") {
  /** @type {Record<string, any>} */
  const next = { ...node, type: nextType, role: node.role || defaultRoleForType(nextType) };

  for (const field of TYPE_SCOPED_FIELDS) {
    delete next[field];
  }

  if (nextType === "file") {
    next.path = typeof node.path === "string" && node.path ? node.path : fallbackPath;
  } else if (nextType === "rag") {
    return withRagDefaults({ ...next, budget_enabled: node.budget_enabled === false ? false : true });
  } else if (nextType === "session_log") {
    if (node.budget_enabled === false) {
      return { ...withoutBudgetFields(next), budget_enabled: false };
    }
    next.budget_enabled = true;
    next.token_budget = typeof node.token_budget === "number" && Number.isFinite(node.token_budget)
      ? node.token_budget
      : DEFAULT_SESSION_LOG_TOKEN_BUDGET;
  }

  return next;
}

/** @param {string} type */
export function nodeTypeBadge(type) {
  const abbr = /** @type {Record<string,string>} */ ({
    selected_persona: "persona",
    active_mods: "mods",
    pinned_characters: "pinned",
    session_log: "log",
    user_note: "note",
    scene_note: "scene",
    current_user_message: "user_msg",
    condition: "cond"
  });
  return abbr[type] || type;
}

/** @param {string} type */
export function nodeTypeCssClass(type) {
  const map = /** @type {Record<string,string>} */ ({
    session_log: "log",
    selected_persona: "persona",
    active_mods: "mods",
    pinned_characters: "pinned",
    user_note: "note",
    scene_note: "note",
    current_user_message: "user",
    condition: "cond"
  });
  return `type-${map[type] || type}`;
}

/** @param {Record<string, any>} node */
export function nodeSubText(node) {
  if (node.type === "file") return node.path || "";
  if (node.type === "rag") {
    const srcs = normalizedRagSources(node);
    return srcs.length ? srcs.join(", ") : "all sources";
  }
  if (node.type === "session_log" && node.token_budget) {
    return `runtime · ${node.token_budget}tok`;
  }
  if (node.type === "active_mods") return "runtime · active mods";
  if (node.type === "pinned_characters") return "runtime · pinned characters";
  return `runtime · ${node.role || "system"}`;
}

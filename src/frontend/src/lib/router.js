import { readable } from "svelte/store";

export const ROUTE_NAMES = {
  front: "front",
  session: "session",
  scenario: "scenario",
  notFound: "not_found"
};

/**
 * @param {URLSearchParams} searchParams
 * @returns {Record<string, string>}
 */
export function parseQuery(searchParams) {
  return Object.fromEntries(searchParams.entries());
}

/**
 * @param {{ pathname: string, search: string }} locationLike
 */
export function parseRoute(locationLike) {
  const path = locationLike.pathname.replace(/\/+$/, "") || "/";
  const query = parseQuery(new URLSearchParams(locationLike.search));

  if (path === "/") {
    return { name: ROUTE_NAMES.front, path, query };
  }

  if (path === "/session") {
    return {
      name: ROUTE_NAMES.session,
      path,
      query,
      scenarioId: query.scenario || "",
      sessionId: query.session || ""
    };
  }

  if (path === "/scenario") {
    return {
      name: ROUTE_NAMES.scenario,
      path,
      query,
      scenarioId: query.scenario || "",
      mode: query.mode || "view"
    };
  }

  return { name: ROUTE_NAMES.notFound, path, query };
}

function currentRoute() {
  if (typeof window === "undefined") {
    return parseRoute({ pathname: "/", search: "" });
  }
  return parseRoute(window.location);
}

export const route = readable(currentRoute(), (set) => {
  if (typeof window === "undefined") {
    return () => {};
  }

  const update = () => set(currentRoute());
  window.addEventListener("popstate", update);
  return () => window.removeEventListener("popstate", update);
});

/**
 * @param {string} path
 * @param {Record<string, string | null | undefined>} [query]
 */
export function navigate(path, query = {}) {
  if (typeof window === "undefined") {
    return;
  }

  const url = new URL(path, window.location.origin);
  for (const [key, value] of Object.entries(query)) {
    if (value !== null && value !== undefined && value !== "") {
      url.searchParams.set(key, value);
    }
  }

  window.history.pushState({}, "", `${url.pathname}${url.search}`);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

import { writable } from "svelte/store";

export function createSessionLayoutStore() {
  const { subscribe, update } = writable({
    sideOpen: false,
    rightOpen: false,
    rightPanel: "state"
  });

  return {
    subscribe,
    /** @param {boolean} open */
    setSideOpen(open) {
      update((state) => ({ ...state, sideOpen: open }));
    },
    /** @param {boolean} open */
    setRightOpen(open) {
      update((state) => ({ ...state, rightOpen: open }));
    },
    /** @param {"state" | "timeline"} panel */
    setRightPanel(panel) {
      update((state) => ({ ...state, rightPanel: panel }));
    },
    /** @param {"state" | "timeline"} panel */
    openRightPanel(panel) {
      update((state) => ({ ...state, rightPanel: panel, rightOpen: true }));
    },
    /**
     * @param {boolean} isMobile
     */
    applyViewportMode(isMobile) {
      update((state) => ({
        ...state,
        sideOpen: !isMobile,
        rightOpen: false
      }));
    }
  };
}

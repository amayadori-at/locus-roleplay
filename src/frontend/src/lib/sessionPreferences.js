import { writable } from "svelte/store";

const STREAM_KEY = "locus_stream_enabled";
const SEND_ON_ENTER_KEY = "locus_send_on_enter";

/**
 * @param {string} key
 * @param {boolean} fallback
 */
function readBool(key, fallback) {
  if (typeof localStorage === "undefined") return fallback;
  const value = localStorage.getItem(key);
  if (value === null) return fallback;
  return value !== "false";
}

/**
 * @param {string} key
 * @param {boolean} value
 */
function writeBool(key, value) {
  if (typeof localStorage === "undefined") return;
  localStorage.setItem(key, String(Boolean(value)));
}

export function createSessionPreferencesStore() {
  const { subscribe, update } = writable({
    streamEnabled: readBool(STREAM_KEY, true),
    sendOnEnter: readBool(SEND_ON_ENTER_KEY, true)
  });

  return {
    subscribe,
    /** @param {boolean} value */
    setStreamEnabled(value) {
      writeBool(STREAM_KEY, value);
      update((state) => ({ ...state, streamEnabled: Boolean(value) }));
    },
    /** @param {boolean} value */
    setSendOnEnter(value) {
      writeBool(SEND_ON_ENTER_KEY, value);
      update((state) => ({ ...state, sendOnEnter: Boolean(value) }));
    }
  };
}

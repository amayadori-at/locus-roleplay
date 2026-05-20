import { writable } from "svelte/store";

/**
 * @typedef {"persona" | "roleplay" | "state" | ""} PickerKind
 *
 * @typedef {{
 *   model: string | number,
 *   temperature: string | number,
 *   top_p: string | number,
 *   top_k: string | number,
 *   context_size: string | number,
 *   max_tokens: string | number,
 *   frequency_penalty: string | number,
 *   presence_penalty: string | number,
 *   repetition_penalty: string | number,
 *   reasoning_effort: string
 * }} PickerProfilePatch
 *
 * @typedef {{
 *   kind: PickerKind,
 *   editId: string,
 *   content: string,
 *   dirty: boolean,
 *   saving: boolean,
 *   error: string,
 *   loadingEdit: boolean,
 *   profilePatch: PickerProfilePatch | null,
 *   creatingPersona: boolean,
 *   newPersonaId: string,
 *   newPersonaName: string,
 *   newPersonaError: string,
 *   newPersonaCreating: boolean
 * }} SessionPickerState
 */

/** @type {SessionPickerState} */
const initialState = {
  kind: "",
  editId: "",
  content: "",
  dirty: false,
  saving: false,
  error: "",
  loadingEdit: false,
  profilePatch: null,
  creatingPersona: false,
  newPersonaId: "",
  newPersonaName: "",
  newPersonaError: "",
  newPersonaCreating: false
};

/** @param {Record<string, any>} data */
export function profileDataToPatch(data) {
  return {
    model: data.model ?? "",
    temperature: data.temperature ?? "",
    top_p: data.top_p ?? "",
    top_k: data.top_k ?? "",
    context_size: data.context_size ?? "",
    max_tokens: data.max_tokens ?? "",
    frequency_penalty: data.frequency_penalty ?? "",
    presence_penalty: data.presence_penalty ?? "",
    repetition_penalty: data.repetition_penalty ?? "",
    reasoning_effort: data.reasoning_effort ?? ""
  };
}

/** @param {PickerProfilePatch} profilePatch */
export function profilePatchToPayload(profilePatch) {
  const patch = /** @type {Record<string, any>} */ ({});
  if (profilePatch.model !== "") patch.model = profilePatch.model;
  const numFields = /** @type {const} */ ([
    "temperature",
    "top_p",
    "top_k",
    "context_size",
    "max_tokens",
    "frequency_penalty",
    "presence_penalty",
    "repetition_penalty"
  ]);
  for (const field of numFields) {
    const value = profilePatch[field];
    if (value !== "" && value !== null && value !== undefined) patch[field] = Number(value);
  }
  if (profilePatch.reasoning_effort !== "") patch.reasoning_effort = profilePatch.reasoning_effort;
  return patch;
}

export function createSessionPickerStore() {
  const { subscribe, set, update } = writable(initialState);

  return {
    subscribe,
    reset: () => set(initialState),
    /** @param {PickerKind} kind */
    open(kind) {
      update((state) => ({
        ...initialState,
        kind,
        newPersonaCreating: false
      }));
    },
    close() {
      set(initialState);
    },
    /** @param {boolean} creating */
    setCreatingPersona(creating) {
      update((state) => ({ ...state, creatingPersona: creating }));
    },
    /** @param {string} value */
    setNewPersonaId(value) {
      update((state) => ({ ...state, newPersonaId: value }));
    },
    /** @param {string} value */
    setNewPersonaName(value) {
      update((state) => ({ ...state, newPersonaName: value }));
    },
    /** @param {string} error */
    setNewPersonaError(error) {
      update((state) => ({ ...state, newPersonaError: error }));
    },
    /** @param {boolean} creating */
    setNewPersonaCreating(creating) {
      update((state) => ({ ...state, newPersonaCreating: creating }));
    },
    /** @param {string} id */
    startPersonaEdit(id) {
      update((state) => ({
        ...state,
        editId: id,
        content: "",
        dirty: false,
        error: "",
        loadingEdit: true,
        profilePatch: null
      }));
    },
    /** @param {string} id */
    startProfileEdit(id) {
      update((state) => ({
        ...state,
        editId: id,
        dirty: false,
        error: "",
        loadingEdit: true,
        profilePatch: null
      }));
    },
    /** @param {boolean} loading */
    setLoadingEdit(loading) {
      update((state) => ({ ...state, loadingEdit: loading }));
    },
    /** @param {string} error */
    setError(error) {
      update((state) => ({ ...state, error }));
    },
    /** @param {string} content */
    setContent(content) {
      update((state) => ({ ...state, content }));
    },
    /** @param {string} content */
    updateContent(content) {
      update((state) => ({ ...state, content, dirty: true }));
    },
    /** @param {PickerProfilePatch | null} profilePatch */
    setProfilePatch(profilePatch) {
      update((state) => ({ ...state, profilePatch }));
    },
    /**
     * @param {keyof PickerProfilePatch} field
     * @param {string} value
     */
    updateProfilePatch(field, value) {
      update((state) => ({
        ...state,
        dirty: true,
        profilePatch: state.profilePatch ? { ...state.profilePatch, [field]: value } : state.profilePatch
      }));
    },
    /** @param {boolean} saving */
    setSaving(saving) {
      update((state) => ({ ...state, saving }));
    },
    markClean() {
      update((state) => ({ ...state, dirty: false }));
    },
    clearNewPersonaForm() {
      update((state) => ({
        ...state,
        creatingPersona: false,
        newPersonaId: "",
        newPersonaName: "",
        newPersonaError: "",
        newPersonaCreating: false
      }));
    }
  };
}

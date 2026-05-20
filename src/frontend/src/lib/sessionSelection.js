import { writable } from "svelte/store";

export const EMPTY_SELECTION = "未選択";

const LS_DEFAULT_RP_PROFILE = "locus_default_rp_profile_id";
const LS_DEFAULT_STATE_PROFILE = "locus_default_state_profile_id";

export function getDefaultRpProfileId() {
  try { return localStorage.getItem(LS_DEFAULT_RP_PROFILE) || null; } catch { return null; }
}

export function setDefaultRpProfileId(/** @type {string} */ id) {
  try { localStorage.setItem(LS_DEFAULT_RP_PROFILE, id); } catch {}
}

export function getDefaultStateProfileId() {
  try { return localStorage.getItem(LS_DEFAULT_STATE_PROFILE) || null; } catch { return null; }
}

export function setDefaultStateProfileId(/** @type {string} */ id) {
  try { localStorage.setItem(LS_DEFAULT_STATE_PROFILE, id); } catch {}
}

/**
 * @typedef {{
 *   id: string,
 *   name?: string
 * }} PersonaSummary
 *
 * @typedef {{
 *   id: string,
 *   kind?: string,
 *   model?: string,
 *   context_size?: number,
 *   temperature?: number,
 *   top_p?: number,
 *   max_tokens?: number
 * }} ProfileSummary
 *
 * @typedef {{
 *   personas: PersonaSummary[],
 *   profiles: ProfileSummary[],
 *   selectedPersona: string,
 *   selectedRpProfile: string,
 *   selectedStateProfile: string
 * }} SessionSelectionState
 */

/** @type {SessionSelectionState} */
const initialState = {
  personas: [],
  profiles: [],
  selectedPersona: EMPTY_SELECTION,
  selectedRpProfile: EMPTY_SELECTION,
  selectedStateProfile: EMPTY_SELECTION
};

/** @param {ProfileSummary[]} profiles */
export function roleplayProfiles(profiles) {
  return profiles.filter((profile) => profile.kind === "roleplay");
}

/** @param {ProfileSummary[]} profiles */
export function stateProfiles(profiles) {
  return profiles.filter((profile) => profile.kind === "state_update" || profile.kind === "memory_summary");
}

/**
 * @param {PersonaSummary[]} personas
 * @param {ProfileSummary[]} profiles
 */
export function defaultSelection(personas, profiles) {
  const persona = personas[0];
  const savedRpId = getDefaultRpProfileId();
  const savedStateId = getDefaultStateProfileId();
  const rpProfile =
    (savedRpId && profiles.find((p) => p.id === savedRpId)) ||
    profiles.find((profile) => profile.kind === "roleplay");
  const summaryProfile =
    (savedStateId && profiles.find((p) => p.id === savedStateId)) ||
    profiles.find((profile) => profile.kind === "state_update") ||
    profiles.find((profile) => profile.kind === "memory_summary");

  return {
    selectedPersona: persona?.id || EMPTY_SELECTION,
    selectedRpProfile: rpProfile?.id || EMPTY_SELECTION,
    selectedStateProfile: summaryProfile?.id || EMPTY_SELECTION
  };
}

/**
 * @param {SessionSelectionState} state
 * @param {string} id
 */
export function personaName(state, id) {
  const persona = state.personas.find((item) => item.id === id);
  return persona?.name || id;
}

/**
 * @param {SessionSelectionState} state
 * @param {string} id
 */
export function profileModel(state, id) {
  const profile = state.profiles.find((item) => item.id === id);
  return profile?.model || "未設定";
}

export function createSessionSelectionStore() {
  const { subscribe, set, update } = writable(initialState);

  return {
    subscribe,
    reset: () => set(initialState),
    /**
     * @param {PersonaSummary[]} personas
     * @param {ProfileSummary[]} profiles
     */
    setChoices: (personas, profiles) =>
      update((state) => ({
        ...state,
        personas,
        profiles
      })),
    applyDefaults: () =>
      update((state) => ({
        ...state,
        ...defaultSelection(state.personas, state.profiles)
      })),
    /** @param {Record<string, unknown>} metadata */
    applyMetadata: (metadata) =>
      update((state) => ({
        ...state,
        selectedPersona:
          typeof metadata.persona_id === "string" ? metadata.persona_id : state.selectedPersona,
        selectedRpProfile:
          typeof metadata.rp_profile_id === "string" ? metadata.rp_profile_id : state.selectedRpProfile,
        selectedStateProfile:
          typeof metadata.summary_profile_id === "string" ? metadata.summary_profile_id : state.selectedStateProfile
      })),
    /** @param {PersonaSummary[]} personas */
    setPersonas: (personas) => update((state) => ({ ...state, personas })),
    /** @param {ProfileSummary[]} profiles */
    setProfiles: (profiles) => update((state) => ({ ...state, profiles })),
    /** @param {string} id */
    choosePersona: (id) => update((state) => ({ ...state, selectedPersona: id })),
    /** @param {string} id */
    chooseRpProfile: (id) => update((state) => ({ ...state, selectedRpProfile: id })),
    /** @param {string} id */
    chooseStateProfile: (id) => update((state) => ({ ...state, selectedStateProfile: id }))
  };
}

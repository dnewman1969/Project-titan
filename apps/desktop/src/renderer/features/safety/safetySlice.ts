import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { SafetyState } from "@titan/protocol";

import type { KillSwitchEvent } from "../../../shared/ipc";

/**
 * Mirrors the protocol `SafetyState`. A kill shows at once (optimistic); the API's state then
 * arrives over WS `system.safety` and wins. Phase 1 never arms.
 */
const initialState: SafetyState = {
  killed: false,
  armed: false,
  control_owner: "none",
  last_kill_at: null,
  last_kill_source: null,
  policy_version: 0,
};

export const safetySlice = createSlice({
  name: "safety",
  initialState,
  reducers: {
    killSwitchTriggered(state, action: PayloadAction<KillSwitchEvent>) {
      state.killed = true;
      state.armed = false;
      state.control_owner = "none";
      state.last_kill_at = action.payload.at;
      state.last_kill_source = action.payload.source;
    },
    safetyStateReceived(_state, action: PayloadAction<SafetyState>) {
      return action.payload;
    },
    /** Without a backend there is no server state to resume, so the banner clears locally. */
    killAcknowledged(state) {
      state.killed = false;
    },
  },
});

export const { killSwitchTriggered, safetyStateReceived, killAcknowledged } = safetySlice.actions;

import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { SafetyState } from "@titan/protocol";

import type { KillSwitchEvent } from "../../../shared/ipc";

/** Mirrors the protocol `SafetyState`. Phase 1 never arms, so a kill is acknowledged locally. */
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
    killAcknowledged(state) {
      state.killed = false;
    },
  },
});

export const { killSwitchTriggered, killAcknowledged } = safetySlice.actions;

import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { SystemMetrics } from "@titan/protocol";

/** Ring buffer size for sparklines (Section 2.13). */
export const METRICS_HISTORY = 600;

interface SystemState {
  latest: SystemMetrics | null;
  history: SystemMetrics[];
}

const initialState: SystemState = { latest: null, history: [] };

/** Fed by the WS `system.metrics` channel once the gateway (M1.T4) and metrics (M1.T6) exist. */
export const systemSlice = createSlice({
  name: "system",
  initialState,
  reducers: {
    metricsReceived(state, action: PayloadAction<SystemMetrics>) {
      state.latest = action.payload;
      state.history.push(action.payload);
      if (state.history.length > METRICS_HISTORY)
        state.history.splice(0, state.history.length - METRICS_HISTORY);
    },
  },
});

export const { metricsReceived } = systemSlice.actions;

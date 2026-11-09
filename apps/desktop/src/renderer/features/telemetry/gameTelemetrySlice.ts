import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { TelemetryFrameUI } from "@titan/protocol";

/** Latest normalized game frame from `session.*.telemetry` (M5.T6 / M7.T4). */
interface GameTelemetryState {
  latest: TelemetryFrameUI | null;
  speedHistory: number[];
}

const initialState: GameTelemetryState = { latest: null, speedHistory: [] };

export const gameTelemetrySlice = createSlice({
  name: "gameTelemetry",
  initialState,
  reducers: {
    telemetryFrameReceived(state, action: PayloadAction<TelemetryFrameUI>) {
      state.latest = action.payload;
      const speed = action.payload.vehicle.velocity?.speed_mps;
      if (typeof speed === "number") {
        state.speedHistory.push(speed);
        if (state.speedHistory.length > 120) state.speedHistory.shift();
      }
    },
  },
});

export const { telemetryFrameReceived } = gameTelemetrySlice.actions;

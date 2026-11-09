import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { GameEvent } from "@titan/protocol";

/**
 * Event log entries. Game events arrive on the WS `events` channel (M5.T6); shell-level events
 * (API connectivity, kill switch) using the protocol's category and severity vocabulary.
 */
export interface LogEntry extends Pick<GameEvent, "type" | "category" | "severity"> {
  id: number;
  at: string;
  text: string;
}

export const MAX_LOG_ENTRIES = 500;

interface EventsState {
  entries: LogEntry[];
  nextId: number;
}

const initialState: EventsState = { entries: [], nextId: 1 };

export const eventsSlice = createSlice({
  name: "events",
  initialState,
  reducers: {
    logEvent: {
      reducer(state, action: PayloadAction<Omit<LogEntry, "id">>) {
        state.entries.unshift({ ...action.payload, id: state.nextId });
        state.nextId += 1;
        if (state.entries.length > MAX_LOG_ENTRIES) state.entries.length = MAX_LOG_ENTRIES;
      },
      prepare(entry: Omit<LogEntry, "id" | "at"> & { at?: string }) {
        return { payload: { ...entry, at: entry.at ?? new Date().toISOString() } };
      },
    },
    clearLog(state) {
      state.entries = [];
    },
  },
});

export const { logEvent, clearLog } = eventsSlice.actions;

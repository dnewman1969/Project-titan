import { createSlice, type PayloadAction } from "@reduxjs/toolkit";

export type SessionDialogKind = "new" | "open" | "replay";

interface SessionsState {
  dialog: SessionDialogKind | null;
  activeSessionId: string | null;
  activeTitle: string | null;
  recordingActive: boolean;
}

const initialState: SessionsState = {
  dialog: null,
  activeSessionId: null,
  activeTitle: null,
  recordingActive: false,
};

export const sessionsSlice = createSlice({
  name: "sessions",
  initialState,
  reducers: {
    openSessionDialog(state, action: PayloadAction<SessionDialogKind>) {
      state.dialog = action.payload;
    },
    closeSessionDialog(state) {
      state.dialog = null;
    },
    setActiveSession(state, action: PayloadAction<{ id: string; title: string }>) {
      state.activeSessionId = action.payload.id;
      state.activeTitle = action.payload.title;
      state.recordingActive = false;
    },
    setRecordingActive(state, action: PayloadAction<boolean>) {
      state.recordingActive = action.payload;
    },
    clearActiveSession(state) {
      state.activeSessionId = null;
      state.activeTitle = null;
      state.recordingActive = false;
    },
  },
});

export const {
  openSessionDialog,
  closeSessionDialog,
  setActiveSession,
  setRecordingActive,
  clearActiveSession,
} = sessionsSlice.actions;

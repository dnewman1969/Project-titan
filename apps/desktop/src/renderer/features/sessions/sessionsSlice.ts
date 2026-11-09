import { createSlice, type PayloadAction } from "@reduxjs/toolkit";

export type SessionDialogKind = "new" | "open" | "replay";

interface SessionsState {
  dialog: SessionDialogKind | null;
  activeSessionId: string | null;
  activeTitle: string | null;
  recordingActive: boolean;
  recordingMenuRequest: "start" | "stop" | null;
}

const initialState: SessionsState = {
  dialog: null,
  activeSessionId: null,
  activeTitle: null,
  recordingActive: false,
  recordingMenuRequest: null,
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
      state.recordingMenuRequest = null;
    },
    requestRecordingFromMenu(state, action: PayloadAction<"start" | "stop">) {
      state.recordingMenuRequest = action.payload;
    },
    clearRecordingMenuRequest(state) {
      state.recordingMenuRequest = null;
    },
  },
});

export const {
  openSessionDialog,
  closeSessionDialog,
  setActiveSession,
  setRecordingActive,
  clearActiveSession,
  requestRecordingFromMenu,
  clearRecordingMenuRequest,
} = sessionsSlice.actions;

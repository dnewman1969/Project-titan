import { createSlice, type PayloadAction } from "@reduxjs/toolkit";

export type SessionDialogKind = "new" | "open" | "replay";

export type SessionSourceKind = "live" | "fixture" | null;

interface SessionsState {
  dialog: SessionDialogKind | null;
  activeSessionId: string | null;
  activeTitle: string | null;
  sessionSource: SessionSourceKind;
  playEnabled: boolean;
  recordingActive: boolean;
  recordingMenuRequest: "start" | "stop" | null;
  recordingRootDir: string | null;
}

const initialState: SessionsState = {
  dialog: null,
  activeSessionId: null,
  activeTitle: null,
  sessionSource: null,
  playEnabled: false,
  recordingActive: false,
  recordingMenuRequest: null,
  recordingRootDir: null,
};

export const sessionsSlice = createSlice({
  name: "sessions",
  initialState,
  reducers: {
    openSessionDialog(state, action: PayloadAction<SessionDialogKind>) {
      state.dialog = action.payload;
      if (typeof localStorage !== "undefined") {
        localStorage.setItem("titan.skipAutoDemo", "1");
      }
    },
    closeSessionDialog(state) {
      state.dialog = null;
    },
    setActiveSession(
      state,
      action: PayloadAction<{
        id: string;
        title: string;
        recordingActive?: boolean;
        recordingRootDir?: string | null;
        sessionSource?: SessionSourceKind;
        playEnabled?: boolean;
      }>,
    ) {
      state.activeSessionId = action.payload.id;
      state.activeTitle = action.payload.title;
      state.recordingActive = action.payload.recordingActive ?? false;
      state.recordingRootDir = action.payload.recordingRootDir ?? null;
      state.sessionSource = action.payload.sessionSource ?? null;
      state.playEnabled = action.payload.playEnabled ?? false;
    },
    setRecordingActive(state, action: PayloadAction<boolean>) {
      state.recordingActive = action.payload;
    },
    clearActiveSession(state) {
      state.activeSessionId = null;
      state.activeTitle = null;
      state.sessionSource = null;
      state.playEnabled = false;
      state.recordingActive = false;
      state.recordingMenuRequest = null;
      state.recordingRootDir = null;
    },
    setRecordingRootDir(state, action: PayloadAction<string | null>) {
      state.recordingRootDir = action.payload;
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
  setRecordingRootDir,
} = sessionsSlice.actions;

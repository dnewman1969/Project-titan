import { createSlice, type PayloadAction } from "@reduxjs/toolkit";

export type SessionDialogKind = "new" | "open" | "replay";

export type SessionSourceKind = "live" | "fixture" | null;

export type PlayBackendKind = "hil" | "krpc" | "scs" | "keyboard" | "auto" | null;

interface SessionsState {
  dialog: SessionDialogKind | null;
  activeSessionId: string | null;
  activeTitle: string | null;
  activeGameSlug: string | null;
  sessionSource: SessionSourceKind;
  playEnabled: boolean;
  playBackend: PlayBackendKind;
  playReady: boolean | null;
  playAttachMessage: string | null;
  recordingActive: boolean;
  recordingMenuRequest: "start" | "stop" | null;
  recordingRootDir: string | null;
}

const initialState: SessionsState = {
  dialog: null,
  activeSessionId: null,
  activeTitle: null,
  activeGameSlug: null,
  sessionSource: null,
  playEnabled: false,
  playBackend: null,
  playReady: null,
  playAttachMessage: null,
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
        playBackend?: PlayBackendKind;
        playReady?: boolean | null;
        playAttachMessage?: string | null;
        gameSlug?: string | null;
      }>,
    ) {
      state.activeSessionId = action.payload.id;
      state.activeTitle = action.payload.title;
      state.activeGameSlug = action.payload.gameSlug ?? null;
      state.recordingActive = action.payload.recordingActive ?? false;
      state.recordingRootDir = action.payload.recordingRootDir ?? null;
      state.sessionSource = action.payload.sessionSource ?? null;
      state.playEnabled = action.payload.playEnabled ?? false;
      state.playBackend = action.payload.playBackend ?? null;
      state.playReady = action.payload.playReady ?? null;
      state.playAttachMessage = action.payload.playAttachMessage ?? null;
    },
    setRecordingActive(state, action: PayloadAction<boolean>) {
      state.recordingActive = action.payload;
    },
    setPlayEnabled(
      state,
      action: PayloadAction<{
        playEnabled: boolean;
        playBackend?: PlayBackendKind;
        playReady?: boolean | null;
        playAttachMessage?: string | null;
      }>,
    ) {
      state.playEnabled = action.payload.playEnabled;
      if (action.payload.playBackend !== undefined) state.playBackend = action.payload.playBackend;
      if (action.payload.playReady !== undefined) state.playReady = action.payload.playReady;
      if (action.payload.playAttachMessage !== undefined) {
        state.playAttachMessage = action.payload.playAttachMessage;
      }
    },
    setPlayAttach(
      state,
      action: PayloadAction<{
        playReady?: boolean | null;
        playAttachMessage?: string | null;
        playBackend?: PlayBackendKind;
      }>,
    ) {
      if (action.payload.playReady !== undefined) state.playReady = action.payload.playReady;
      if (action.payload.playAttachMessage !== undefined) {
        state.playAttachMessage = action.payload.playAttachMessage;
      }
      if (action.payload.playBackend !== undefined) state.playBackend = action.payload.playBackend;
    },
    clearActiveSession(state) {
      state.activeSessionId = null;
      state.activeTitle = null;
      state.activeGameSlug = null;
      state.sessionSource = null;
      state.playEnabled = false;
      state.playBackend = null;
      state.playReady = null;
      state.playAttachMessage = null;
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
  setPlayEnabled,
  setPlayAttach,
  clearActiveSession,
  requestRecordingFromMenu,
  clearRecordingMenuRequest,
  setRecordingRootDir,
} = sessionsSlice.actions;

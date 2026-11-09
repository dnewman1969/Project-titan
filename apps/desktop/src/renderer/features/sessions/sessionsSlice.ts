import { createSlice, type PayloadAction } from "@reduxjs/toolkit";

export type SessionDialogKind = "new" | "open" | "replay";

interface SessionsState {
  dialog: SessionDialogKind | null;
}

const initialState: SessionsState = { dialog: null };

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
  },
});

export const { openSessionDialog, closeSessionDialog } = sessionsSlice.actions;

import { createSlice, type PayloadAction } from "@reduxjs/toolkit";

import type { PanelId } from "../../../shared/menu";

export interface LayoutState {
  panels: Record<PanelId, boolean>;
  notice: { id: number; text: string } | null;
  aboutOpen: boolean;
}

const initialState: LayoutState = {
  panels: { agents: true, webcam: true, telemetry: true, events: true, games: false },
  notice: null,
  aboutOpen: false,
};

export const layoutSlice = createSlice({
  name: "layout",
  initialState,
  reducers: {
    togglePanel(state, action: PayloadAction<PanelId>) {
      state.panels[action.payload] = !state.panels[action.payload];
    },
    showNotice(state, action: PayloadAction<string>) {
      state.notice = { id: (state.notice?.id ?? 0) + 1, text: action.payload };
    },
    dismissNotice(state) {
      state.notice = null;
    },
    setAboutOpen(state, action: PayloadAction<boolean>) {
      state.aboutOpen = action.payload;
    },
  },
});

export const { togglePanel, showNotice, dismissNotice, setAboutOpen } = layoutSlice.actions;

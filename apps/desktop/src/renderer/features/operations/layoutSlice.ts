import { createSlice, type PayloadAction } from "@reduxjs/toolkit";

import type { PanelId } from "../../../shared/menu";
import type { SettingsDocument } from "../../app/settings";
import { panelsFromSettings } from "../../app/settings";

export interface LayoutState {
  panels: Record<PanelId, boolean>;
  /** `settings.version` from GET /settings; used for optimistic concurrency on PATCH. */
  settingsVersion: number | null;
  settingsHydrated: boolean;
  notice: { id: number; text: string } | null;
  aboutOpen: boolean;
  firstRunOpen: boolean;
}

const initialState: LayoutState = {
  panels: { agents: true, webcam: true, telemetry: true, events: true, games: false },
  settingsVersion: null,
  settingsHydrated: false,
  notice: null,
  aboutOpen: false,
  firstRunOpen: false,
};

export const layoutSlice = createSlice({
  name: "layout",
  initialState,
  reducers: {
    togglePanel(state, action: PayloadAction<PanelId>) {
      state.panels[action.payload] = !state.panels[action.payload];
    },
    showPanel(state, action: PayloadAction<PanelId>) {
      state.panels[action.payload] = true;
    },
    hydrateFromSettings(state, action: PayloadAction<SettingsDocument>) {
      state.panels = panelsFromSettings(action.payload.values, state.panels);
      state.settingsVersion = action.payload.version;
      state.settingsHydrated = true;
    },
    setSettingsVersion(state, action: PayloadAction<number>) {
      state.settingsVersion = action.payload;
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
    setFirstRunOpen(state, action: PayloadAction<boolean>) {
      state.firstRunOpen = action.payload;
    },
  },
});

export const {
  togglePanel,
  showPanel,
  hydrateFromSettings,
  setSettingsVersion,
  showNotice,
  dismissNotice,
  setAboutOpen,
  setFirstRunOpen,
} = layoutSlice.actions;

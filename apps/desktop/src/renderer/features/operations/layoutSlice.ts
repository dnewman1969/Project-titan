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
  /** Stays on the session bar until the next successful play toggle. */
  sessionBarError: string | null;
  /** Stays beside REC until the next start or stop attempt. */
  transportError: string | null;
  gamesOpen: boolean;
  aboutOpen: boolean;
  firstRunOpen: boolean;
  krpcObsHelpOpen: boolean;
  publishOpen: boolean;
  memoryBrowserOpen: boolean;
}

const initialState: LayoutState = {
  panels: { crew: true, webcam: true, contract: true, telemetry: true, events: false },
  settingsVersion: null,
  settingsHydrated: false,
  notice: null,
  sessionBarError: null,
  transportError: null,
  gamesOpen: false,
  aboutOpen: false,
  firstRunOpen: false,
  krpcObsHelpOpen: false,
  publishOpen: false,
  memoryBrowserOpen: false,
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
    setPanel(state, action: PayloadAction<{ id: PanelId; on: boolean }>) {
      state.panels[action.payload.id] = action.payload.on;
    },
    setSessionBarError(state, action: PayloadAction<string | null>) {
      state.sessionBarError = action.payload;
    },
    setTransportError(state, action: PayloadAction<string | null>) {
      state.transportError = action.payload;
    },
    setGamesOpen(state, action: PayloadAction<boolean>) {
      state.gamesOpen = action.payload;
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
    setKrpcObsHelpOpen(state, action: PayloadAction<boolean>) {
      state.krpcObsHelpOpen = action.payload;
    },
    setPublishOpen(state, action: PayloadAction<boolean>) {
      state.publishOpen = action.payload;
    },
    setMemoryBrowserOpen(state, action: PayloadAction<boolean>) {
      state.memoryBrowserOpen = action.payload;
    },
  },
});

export const {
  togglePanel,
  showPanel,
  setPanel,
  setSessionBarError,
  setTransportError,
  setGamesOpen,
  hydrateFromSettings,
  setSettingsVersion,
  showNotice,
  dismissNotice,
  setAboutOpen,
  setFirstRunOpen,
  setKrpcObsHelpOpen,
  setPublishOpen,
  setMemoryBrowserOpen,
} = layoutSlice.actions;

import { createListenerMiddleware, isAnyOf } from "@reduxjs/toolkit";

import { setSettingsVersion, togglePanel } from "../features/operations/layoutSlice";
import { titanApi } from "./api";
import { getTitan } from "./runtime";
import type { AppDispatch, RootState } from "./store";

export const layoutPersistListener = createListenerMiddleware();

layoutPersistListener.startListening({
  matcher: isAnyOf(togglePanel),
  effect: async (_action, api) => {
    const state = api.getState() as RootState;
    if (!state.layout.settingsHydrated || state.layout.settingsVersion === null) return;
    if (getTitan().backend === "none") return;
    const version = state.layout.settingsVersion;
    const panels = state.layout.panels;
    try {
      const updated = await (api.dispatch as AppDispatch)(
        titanApi.endpoints.patchSettings.initiate({
          version,
          patch: { "ui.layout": { panels } },
        }),
      ).unwrap();
      api.dispatch(setSettingsVersion(updated.version));
    } catch {
      // Version mismatch or offline: next GET can resync.
    }
  },
});

import { useEffect } from "react";

import { logEvent } from "../features/events/eventsSlice";
import { handleMenuCommand } from "../features/operations/commands";
import { killSwitchTriggered } from "../features/safety/safetySlice";
import { clearActiveSession } from "../features/sessions/sessionsSlice";
import type { KillSwitchEvent } from "../../shared/ipc";
import { appStore, type AppDispatch } from "./store";
import { useAppDispatch } from "./hooks";
import { getTitan } from "./runtime";
import { titanApi } from "./api";

export function triggerKill(dispatch: AppDispatch, event: KillSwitchEvent): void {
  dispatch(killSwitchTriggered(event));
  dispatch(clearActiveSession());
  if (typeof localStorage !== "undefined") {
    localStorage.setItem("titan.skipAutoDemo", "1");
  }
  dispatch(
    logEvent({
      type: "safety.kill",
      category: "safety",
      severity: "critical",
      text: `Kill switch engaged (${event.source}). Live session cleared locally; API ends sticky live rows (Resume before New session).`,
      at: event.at,
    }),
  );
}

/** Wires the preload bridge (menu commands and the global kill-switch hotkey) into the store. */
export function useShellBridge(): void {
  const dispatch = useAppDispatch();
  useEffect(() => {
    const titan = getTitan();
    const offKill = titan.onKillSwitch((event) => {
      const sid = appStore.getState().sessions.activeSessionId;
      triggerKill(dispatch, event);
      if (titan.backend !== "none" && sid) {
        void dispatch(
          titanApi.endpoints.stopSession.initiate({ sessionId: sid, outcome: "aborted" }),
        );
      }
    });
    const offMenu = titan.onMenuCommand((id) => {
      handleMenuCommand(id, dispatch, () => appStore.getState());
    });
    return () => {
      offKill();
      offMenu();
    };
  }, [dispatch]);
}

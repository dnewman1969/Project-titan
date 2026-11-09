import { useEffect } from "react";

import { logEvent } from "../features/events/eventsSlice";
import { handleMenuCommand } from "../features/operations/commands";
import { killSwitchTriggered } from "../features/safety/safetySlice";
import type { KillSwitchEvent } from "../../shared/ipc";
import { appStore, type AppDispatch } from "./store";
import { useAppDispatch } from "./hooks";
import { getTitan } from "./runtime";

export function triggerKill(dispatch: AppDispatch, event: KillSwitchEvent): void {
  dispatch(killSwitchTriggered(event));
  dispatch(
    logEvent({
      type: "safety.kill",
      category: "safety",
      severity: "critical",
      text: `Kill switch engaged (${event.source}). Phase 1 has no AI input path, so nothing needed stopping.`,
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
      triggerKill(dispatch, event);
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

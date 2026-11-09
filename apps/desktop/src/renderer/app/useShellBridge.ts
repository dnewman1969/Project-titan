import { useEffect } from "react";

import { handleMenuCommand } from "../features/operations/commands";
import { triggerKill } from "../features/safety/engageKill";
import { appStore } from "./store";
import { useAppDispatch } from "./hooks";
import { getTitan } from "./runtime";
import { titanApi } from "./api";

/** Wires the preload bridge (menu commands and the global kill-switch hotkey) into the store. */
export function useShellBridge(): void {
  const dispatch = useAppDispatch();
  useEffect(() => {
    const titan = getTitan();
    const offKill = titan.onKillSwitch((event) => {
      const sid = appStore.getState().sessions.activeSessionId;
      triggerKill(dispatch, event);
      if (titan.backend !== "none" && sid) {
        void dispatch(titanApi.endpoints.stopSession.initiate({ sessionId: sid, outcome: "aborted" }));
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

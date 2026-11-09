import type { KillSwitchEvent } from "../../../shared/ipc";
import { titanApi } from "../../app/api";
import { getTitan } from "../../app/runtime";
import { appStore, type AppDispatch } from "../../app/store";
import { logEvent } from "../events/eventsSlice";
import { clearActiveSession } from "../sessions/sessionsSlice";
import { killSwitchTriggered } from "./safetySlice";

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

/** Same path as the status-bar Kill button: local state, end the live session, POST /safety/kill. */
export function engageKill(dispatch: AppDispatch): void {
  const sid = appStore.getState().sessions.activeSessionId;
  triggerKill(dispatch, { source: "button", at: new Date().toISOString() });
  if (getTitan().backend === "none") return;
  if (sid) {
    void dispatch(titanApi.endpoints.stopSession.initiate({ sessionId: sid, outcome: "aborted" }));
  }
  void dispatch(titanApi.endpoints.kill.initiate("button"));
}

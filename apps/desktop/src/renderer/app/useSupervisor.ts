import { SupervisorStatusSchema } from "@titan/protocol";
import { useEffect } from "react";

import { logEvent } from "../features/events/eventsSlice";
import { describeSupervisorEvent, supervisorReceived } from "../features/system/supervisorSlice";
import type { SupervisorUpdate } from "../../shared/ipc";
import { useAppDispatch, useAppStore } from "./hooks";
import { getTitan } from "./runtime";

/** Supervisor updates from Electron main into the store; new supervisor events into the event log. */
export function useSupervisor(): void {
  const dispatch = useAppDispatch();
  const store = useAppStore();
  useEffect(() => {
    const titan = getTitan();
    if (titan.backend !== "managed") return;
    const receive = (update: SupervisorUpdate | null) => {
      if (!update) return;
      const parsed = update.status === null ? null : SupervisorStatusSchema.safeParse(update.status);
      if (parsed && !parsed.success) {
        console.warn("invalid supervisor status", parsed.error.issues);
        return;
      }
      const status = parsed?.data ?? null;
      const lastSeq = store.getState().supervisor.lastSeq;
      for (const event of status?.events ?? []) {
        if (event.seq <= lastSeq) continue;
        const { severity, text } = describeSupervisorEvent(event);
        dispatch(
          logEvent({ type: `supervisor.${event.kind}`, category: "system", severity, text, at: event.ts }),
        );
      }
      dispatch(supervisorReceived({ process: update.process, detail: update.detail, status }));
    };
    const off = titan.onSupervisorUpdate(receive);
    void titan.getSupervisorStatus().then(receive);
    return off;
  }, [dispatch, store]);
}

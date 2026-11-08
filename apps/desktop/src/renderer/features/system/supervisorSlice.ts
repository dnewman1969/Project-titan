import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { ServiceState, SupervisorEvent, SupervisorStatus } from "@titan/protocol";
import type { Status } from "@titan/ui-kit";

import type { SupervisorProcessState } from "../../../shared/ipc";

/** titan-supervisor as reported by Electron main (managed backend only). Drives the boot splash. */
interface SupervisorState {
  process: SupervisorProcessState | null;
  detail: string | null;
  status: SupervisorStatus | null;
  lastSeq: number;
  splashDismissed: boolean;
}

const initialState: SupervisorState = {
  process: null,
  detail: null,
  status: null,
  lastSeq: 0,
  splashDismissed: false,
};

export interface SupervisorReceived {
  process: SupervisorProcessState;
  detail: string | null;
  status: SupervisorStatus | null;
}

export const supervisorSlice = createSlice({
  name: "supervisor",
  initialState,
  reducers: {
    supervisorReceived(state, action: PayloadAction<SupervisorReceived>) {
      state.process = action.payload.process;
      state.detail = action.payload.detail;
      const status = action.payload.status;
      if (status) {
        state.status = status;
        const seqs = status.events.map((e) => e.seq);
        if (seqs.length) state.lastSeq = Math.max(state.lastSeq, ...seqs);
      }
    },
    splashDismissed(state) {
      state.splashDismissed = true;
    },
  },
});

export const { supervisorReceived, splashDismissed } = supervisorSlice.actions;

export const SERVICE_STATUS: Record<ServiceState["state"], Status> = {
  up: "ok",
  degraded: "degraded",
  starting: "degraded",
  down: "down",
  failed: "down",
  stopped: "down",
  unknown: "unknown",
};

const SEVERITY: Record<SupervisorEvent["kind"], "info" | "notice" | "warning" | "critical"> = {
  starting: "info",
  healthy: "info",
  adopted: "notice",
  stopped: "info",
  restarting: "notice",
  unhealthy: "warning",
  exited: "warning",
  circuit_open: "critical",
};

const VERB: Record<SupervisorEvent["kind"], string> = {
  starting: "starting",
  healthy: "healthy",
  adopted: "already running, adopted",
  stopped: "stopped",
  restarting: "restarting",
  unhealthy: "failing health checks",
  exited: "exited",
  circuit_open: "failed repeatedly; restarts stopped (use Restart in the boot screen)",
};

/** Event log line for a supervisor event (M1 acceptance: restarts are logged). */
export function describeSupervisorEvent(event: SupervisorEvent): {
  severity: (typeof SEVERITY)[SupervisorEvent["kind"]];
  text: string;
} {
  const detail = event.detail ? ` (${event.detail})` : "";
  return { severity: SEVERITY[event.kind], text: `${event.process} ${VERB[event.kind]}${detail}` };
}

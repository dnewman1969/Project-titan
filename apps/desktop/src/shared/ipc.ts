/** IPC channel names and the `window.titan` bridge contract (Section 2.13). */
export const IPC = {
  runtime: "titan:runtime",
  menu: "titan:menu",
  killSwitch: "titan:kill-switch",
  supervisor: "titan:supervisor",
  supervisorSnapshot: "titan:supervisor-snapshot",
} as const;

/**
 * How the backend is provided in this launch:
 * - `managed`: Electron runs titan-supervisor, which runs Postgres, Chroma, migrations and the API.
 * - `external`: someone started the supervisor or API by hand with `TITAN_LAUNCH_TOKEN`.
 * - `none`: no backend (packaged builds until Python is bundled in M10, or `TITAN_BACKEND=none`).
 */
export type BackendMode = "managed" | "external" | "none";

export interface TitanRuntime {
  apiBase: string;
  token: string;
  platform: string;
  backend: BackendMode;
  killHotkey: string;
  versions: { app: string; electron: string; chrome: string; node: string };
}

export interface KillSwitchEvent {
  source: "hotkey" | "button";
  at: string;
}

/** The supervisor process as Electron main sees it. */
export type SupervisorProcessState = "starting" | "running" | "restarting" | "exited" | "stopping";

/**
 * Pushed on every poll. `status` is the supervisor's raw `/status` JSON (validated in the renderer
 * against `SupervisorStatusSchema`) carrying only events the renderer has not seen; the snapshot
 * from `getSupervisorStatus()` carries the most recent events instead.
 */
export interface SupervisorUpdate {
  process: SupervisorProcessState;
  detail: string | null;
  status: unknown;
}

export interface TitanBridge extends TitanRuntime {
  onKillSwitch(listener: (event: KillSwitchEvent) => void): () => void;
  onMenuCommand(listener: (id: string) => void): () => void;
  onSupervisorUpdate(listener: (update: SupervisorUpdate) => void): () => void;
  getSupervisorStatus(): Promise<SupervisorUpdate | null>;
}

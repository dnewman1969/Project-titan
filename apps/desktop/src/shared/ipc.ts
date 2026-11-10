/** IPC channel names and the `window.titan` bridge contract (Section 2.13). */
export const IPC = {
  runtime: "titan:runtime",
  menu: "titan:menu",
  killSwitch: "titan:kill-switch",
  supervisor: "titan:supervisor",
  supervisorSnapshot: "titan:supervisor-snapshot",
  openPath: "titan:open-path",
  openExternal: "titan:open-external",
  pickExecutable: "titan:pick-executable",
  gameViewSync: "titan:game-view-sync",
  gameViewConfigure: "titan:game-view-configure",
  gameViewHold: "titan:game-view-hold",
  gameViewFocus: "titan:game-view-focus",
  gameViewStatus: "titan:game-view-status",
  gameViewSnapshot: "titan:game-view-snapshot",
  rendererCommitted: "titan:renderer-committed",
} as const;

/** CSS pixels of the game viewport, relative to the Electron page. */
export interface GameViewRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface GameViewTarget {
  gameSlug: string | null;
  pid: number | null;
}

/** Where the running game sits relative to the Operations Center preview. */
export interface GameViewStatus {
  attached: boolean;
  /** `embed` is SetParent. `dock` is a borderless window locked to the preview. */
  mode: "embed" | "dock" | null;
  title: string | null;
  exe: string | null;
  pid: number | null;
  reason: string | null;
}

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
  /** Open a local folder in the OS file manager (recording dir, logs, etc.). */
  openPath(path: string): Promise<string>;
  openExternal(url: string): Promise<void>;
  /** Native file picker for a game .exe (Windows). Returns null when cancelled. */
  pickExecutable(): Promise<string | null>;
  /** Page-relative rectangle of the live game viewport. */
  gameViewSync(rect: GameViewRect): void;
  /** Which game the preview should prefer, plus the pid Titan just launched. */
  gameViewConfigure(target: GameViewTarget): void;
  /** Hide the docked game while a modal covers the preview, or while there is nothing to dock. */
  gameViewHold(reason: "modal" | "nodock", on: boolean): void;
  /** The React tree has committed. Main uses this to relayout, not the blank ready-to-show frame. */
  rendererCommitted(): void;
  /** Hand keyboard focus to the game window sitting in the preview. */
  gameViewFocus(): void;
  onGameViewStatus(listener: (status: GameViewStatus) => void): () => void;
  getGameViewStatus(): Promise<GameViewStatus>;
}

import type { GameViewStatus, TitanBridge } from "../../shared/ipc";

const IDLE_GAME_VIEW: GameViewStatus = {
  attached: false,
  mode: null,
  title: null,
  exe: null,
  pid: null,
  reason: null,
};

declare global {
  interface Window {
    titan?: TitanBridge;
  }
}

/** Used when the renderer runs outside Electron (tests, or a plain browser pointed at the dev server). */
const BROWSER_FALLBACK: TitanBridge = {
  apiBase: "http://127.0.0.1:8765",
  token: "",
  platform: "browser",
  backend: "none",
  killHotkey: "Ctrl+Shift+F12",
  versions: { app: "dev", electron: "n/a", chrome: "n/a", node: "n/a" },
  onKillSwitch: () => () => undefined,
  onMenuCommand: () => () => undefined,
  onSupervisorUpdate: () => () => undefined,
  getSupervisorStatus: () => Promise.resolve(null),
  openPath: () => Promise.resolve("unavailable"),
  openExternal: () => Promise.resolve(),
  pickExecutable: () => Promise.resolve(null),
  gameViewSync: () => undefined,
  gameViewConfigure: () => undefined,
  gameViewHold: () => undefined,
  gameViewFocus: () => undefined,
  onGameViewStatus: () => () => undefined,
  getGameViewStatus: () => Promise.resolve(IDLE_GAME_VIEW),
};

export function getTitan(): TitanBridge {
  return window.titan ?? BROWSER_FALLBACK;
}

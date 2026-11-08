import type { TitanBridge } from "../../shared/ipc";

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
};

export function getTitan(): TitanBridge {
  return window.titan ?? BROWSER_FALLBACK;
}

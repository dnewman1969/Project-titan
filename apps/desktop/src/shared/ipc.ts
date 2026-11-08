/** IPC channel names and the `window.titan` bridge contract (Section 2.13). */
export const IPC = {
  runtime: "titan:runtime",
  menu: "titan:menu",
  killSwitch: "titan:kill-switch",
} as const;

/** How the API process is provided in this launch. M1.T5 replaces "managed" with titan-supervisor. */
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

export interface TitanBridge extends TitanRuntime {
  onKillSwitch(listener: (event: KillSwitchEvent) => void): () => void;
  onMenuCommand(listener: (id: string) => void): () => void;
}

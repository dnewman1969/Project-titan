/**
 * Sandboxed preload: exposes `window.titan` (Section 2.13) and nothing else. No Node APIs reach
 * the renderer.
 */
import { contextBridge, ipcRenderer, type IpcRendererEvent } from "electron";

import { IPC, type KillSwitchEvent, type TitanBridge, type TitanRuntime } from "../shared/ipc";

const runtime = ipcRenderer.sendSync(IPC.runtime) as TitanRuntime | null;
if (!runtime) throw new Error("Titan runtime unavailable: renderer origin rejected by the main process");

function subscribe(channel: string, listener: (payload: unknown) => void): () => void {
  const handler = (_event: IpcRendererEvent, payload: unknown) => {
    listener(payload);
  };
  ipcRenderer.on(channel, handler);
  return () => {
    ipcRenderer.removeListener(channel, handler);
  };
}

const bridge: TitanBridge = {
  ...runtime,
  onKillSwitch: (listener) =>
    subscribe(IPC.killSwitch, (payload) => {
      listener(payload as KillSwitchEvent);
    }),
  onMenuCommand: (listener) =>
    subscribe(IPC.menu, (payload) => {
      if (typeof payload === "string") listener(payload);
    }),
};

contextBridge.exposeInMainWorld("titan", bridge);

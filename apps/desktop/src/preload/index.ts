/**
 * Sandboxed preload: exposes `window.titan` (Section 2.13) and nothing else. No Node APIs reach
 * the renderer.
 */
import { contextBridge, ipcRenderer, type IpcRendererEvent } from "electron";

import {
  IPC,
  type KillSwitchEvent,
  type SupervisorUpdate,
  type TitanBridge,
  type TitanRuntime,
} from "../shared/ipc";

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
  onSupervisorUpdate: (listener) =>
    subscribe(IPC.supervisor, (payload) => {
      listener(payload as SupervisorUpdate);
    }),
  getSupervisorStatus: () => ipcRenderer.invoke(IPC.supervisorSnapshot) as Promise<SupervisorUpdate | null>,
  openPath: (path: string) => ipcRenderer.invoke(IPC.openPath, path) as Promise<string>,
  openExternal: (url: string) => ipcRenderer.invoke(IPC.openExternal, url) as Promise<void>,
  pickExecutable: () => ipcRenderer.invoke(IPC.pickExecutable) as Promise<string | null>,
};

contextBridge.exposeInMainWorld("titan", bridge);

/**
 * Sandboxed preload: exposes `window.titan` (Section 2.13) and nothing else. No Node APIs reach
 * the renderer.
 */
import { contextBridge, ipcRenderer, type IpcRendererEvent } from "electron";

import {
  IPC,
  type GameViewRect,
  type GameViewStatus,
  type GameViewTarget,
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
  gameViewSync: (rect: GameViewRect) => {
    ipcRenderer.send(IPC.gameViewSync, rect);
  },
  gameViewConfigure: (target: GameViewTarget) => {
    ipcRenderer.send(IPC.gameViewConfigure, target);
  },
  gameViewHold: (reason, on) => {
    ipcRenderer.send(IPC.gameViewHold, { reason, on });
  },
  rendererCommitted: () => {
    ipcRenderer.send(IPC.rendererCommitted);
  },
  gameViewFocus: () => {
    ipcRenderer.send(IPC.gameViewFocus);
  },
  onGameViewStatus: (listener) =>
    subscribe(IPC.gameViewStatus, (payload) => {
      listener(payload as GameViewStatus);
    }),
  getGameViewStatus: () => ipcRenderer.invoke(IPC.gameViewSnapshot) as Promise<GameViewStatus>,
};

contextBridge.exposeInMainWorld("titan", bridge);

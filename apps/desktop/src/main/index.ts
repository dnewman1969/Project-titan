/**
 * Electron main process: window, menu, kill-switch hotkey, launch token and the titan-supervisor
 * lifecycle (Sections 2.2, 2.13 and 9.6, M1.T5).
 */
import type { ChildProcess } from "node:child_process";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

import {
  app,
  BrowserWindow,
  dialog,
  globalShortcut,
  ipcMain,
  Menu,
  net,
  protocol,
  session,
  shell,
  type OpenDialogOptions,
} from "electron";

import { IPC, type KillSwitchEvent, type SupervisorUpdate, type TitanRuntime } from "../shared/ipc";
import { DOCS_URL } from "../shared/menu";
import { resolveMainConfig } from "./config";
import { postKill, registerKillSwitch } from "./killSwitch";
import { buildMenuTemplate } from "./menu";
import { APP_INDEX_URL, APP_ORIGIN, APP_SCHEME, isAppUrl, resolveAppFile } from "./navigation";
import {
  CrashBudget,
  startSupervisor,
  stopSupervisor,
  SupervisorClient,
  SupervisorMonitor,
} from "./supervisor";

const devServerUrl = app.isPackaged ? undefined : process.env.ELECTRON_RENDERER_URL;
const config = resolveMainConfig(process.env, { isPackaged: app.isPackaged, appPath: app.getAppPath() });
const rendererDir = join(__dirname, "../renderer");

protocol.registerSchemesAsPrivileged([
  { scheme: APP_SCHEME, privileges: { standard: true, secure: true, supportFetchAPI: true } },
]);

let mainWindow: BrowserWindow | null = null;
let supervisorProcess: ChildProcess | null = null;
let supervisorStopped = false;
let quitting = false;
let disposeKillSwitch: () => void = () => undefined;

const supervisorClient = new SupervisorClient(config.supervisorBase, config.token);
const monitor = new SupervisorMonitor(supervisorClient, (update: SupervisorUpdate) => {
  sendToRenderer(IPC.supervisor, update);
});
const crashBudget = new CrashBudget();

function runtime(): TitanRuntime {
  return {
    apiBase: config.apiBase,
    token: config.token,
    platform: process.platform,
    backend: config.backend,
    killHotkey: config.killHotkey,
    versions: {
      app: app.getVersion(),
      electron: process.versions.electron,
      chrome: process.versions.chrome,
      node: process.versions.node,
    },
  };
}

function sendToRenderer(channel: string, payload: unknown): void {
  if (mainWindow && !mainWindow.isDestroyed()) mainWindow.webContents.send(channel, payload);
}

function createWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1600,
    height: 1000,
    minWidth: 1180,
    minHeight: 760,
    show: false,
    title: "Titan",
    backgroundColor: "#0b0e14",
    webPreferences: {
      preload: join(__dirname, "../preload/index.js"),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      webSecurity: true,
      allowRunningInsecureContent: false,
      webviewTag: false,
      spellcheck: false,
      devTools: !app.isPackaged,
    },
  });
  win.once("ready-to-show", () => {
    win.show();
  });
  win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  win.webContents.on("will-navigate", (event, url) => {
    if (!isAppUrl(url, devServerUrl)) event.preventDefault();
  });
  void win.loadURL(devServerUrl ?? APP_INDEX_URL);
  return win;
}

function serveRenderer(): void {
  protocol.handle(APP_SCHEME, (request) => {
    const file = resolveAppFile(rendererDir, request.url);
    if (!file) return new Response("Not found", { status: 404 });
    return net.fetch(pathToFileURL(file).toString());
  });
}

function harden(): void {
  app.on("web-contents-created", (_event, contents) => {
    contents.on("will-attach-webview", (event) => {
      event.preventDefault();
    });
    contents.setWindowOpenHandler(() => ({ action: "deny" }));
  });
  // Camera and screen capture arrive with the webcam and game preview panels (M7); deny until then.
  session.defaultSession.setPermissionRequestHandler((_contents, _permission, callback) => {
    callback(false);
  });
  session.defaultSession.setPermissionCheckHandler(() => false);
}

ipcMain.on(IPC.runtime, (event) => {
  event.returnValue = isAppUrl(event.senderFrame?.url, devServerUrl) ? runtime() : null;
});

ipcMain.handle(IPC.supervisorSnapshot, (event) =>
  isAppUrl(event.senderFrame?.url, devServerUrl) && config.backend === "managed" ? monitor.snapshot() : null,
);

ipcMain.handle(IPC.openPath, (event, path: unknown) => {
  if (!isAppUrl(event.senderFrame?.url, devServerUrl)) return "blocked";
  if (typeof path !== "string" || path.length === 0) return "invalid";
  return shell.openPath(path);
});

ipcMain.handle(IPC.openExternal, (event, url: unknown) => {
  if (!isAppUrl(event.senderFrame?.url, devServerUrl)) return;
  if (typeof url !== "string" || !/^https?:\/\//i.test(url)) return;
  void shell.openExternal(url);
});

ipcMain.handle(IPC.pickExecutable, async (event) => {
  if (!isAppUrl(event.senderFrame?.url, devServerUrl)) return null;
  const parent =
    (mainWindow && !mainWindow.isDestroyed() ? mainWindow : null) ?? BrowserWindow.getFocusedWindow();
  const dialogOpts: OpenDialogOptions = {
    title: "Select game executable",
    properties: ["openFile"],
    filters: [
      { name: "Game executable", extensions: ["exe"] },
      { name: "All files", extensions: ["*"] },
    ],
  };
  const result = parent
    ? await dialog.showOpenDialog(parent, dialogOpts)
    : await dialog.showOpenDialog(dialogOpts);
  if (result.canceled || result.filePaths.length === 0) return null;
  return result.filePaths[0] ?? null;
});

function launchSupervisor(): void {
  const child = startSupervisor({
    repoRoot: config.repoRoot,
    token: config.token,
    apiPort: config.apiPort,
    supervisorPort: config.supervisorPort,
    corsOrigins: devServerUrl ? [APP_ORIGIN, new URL(devServerUrl).origin] : [APP_ORIGIN],
  });
  supervisorProcess = child;
  child.on("exit", (code, signal) => {
    console.log(`[supervisor] exited code=${String(code)} signal=${String(signal)}`);
    if (quitting) return;
    if (crashBudget.allowRestart()) {
      monitor.setProcess("restarting", `exited (code ${String(code)}); restarting`);
      setTimeout(launchSupervisor, 2000);
    } else {
      monitor.setProcess("exited", `exited (code ${String(code)}) repeatedly; restart Titan`);
    }
  });
}

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (!mainWindow) return;
    if (mainWindow.isMinimized()) mainWindow.restore();
    mainWindow.focus();
  });

  void app.whenReady().then(() => {
    harden();
    serveRenderer();
    Menu.setApplicationMenu(
      Menu.buildFromTemplate(
        buildMenuTemplate(
          {
            send: (id) => {
              sendToRenderer(IPC.menu, id);
            },
            openDocs: () => void shell.openExternal(DOCS_URL),
          },
          { dev: !app.isPackaged },
        ),
      ),
    );

    const killSwitch = registerKillSwitch(globalShortcut, config.killHotkey, (event: KillSwitchEvent) => {
      console.log(`[kill-switch] ${event.source} at ${event.at}`);
      sendToRenderer(IPC.killSwitch, event);
      if (config.backend !== "none") {
        void postKill(config.apiBase, config.token, event.source).then((result) => {
          if (result !== 200) console.warn(`[kill-switch] /safety/kill: ${String(result)}`);
        });
      }
    });
    if (!killSwitch.registered) console.warn(`[kill-switch] could not register ${config.killHotkey}`);
    disposeKillSwitch = killSwitch.dispose;

    if (config.backend === "managed") {
      launchSupervisor();
      monitor.start();
    }

    mainWindow = createWindow();
    mainWindow.on("closed", () => {
      mainWindow = null;
    });
  });

  app.on("window-all-closed", () => {
    app.quit();
  });

  // Quitting waits for the supervisor to stop every service in order (M1 acceptance: no Titan
  // process survives the app), with a tree kill as the fallback.
  app.on("before-quit", (event) => {
    const child = supervisorProcess;
    if (!child || supervisorStopped) return;
    event.preventDefault();
    if (quitting) return;
    quitting = true;
    monitor.setProcess("stopping");
    monitor.stop();
    void stopSupervisor(child, supervisorClient).then((result) => {
      console.log(`[supervisor] stop: ${result}`);
      supervisorStopped = true;
      app.quit();
    });
  });

  app.on("will-quit", () => {
    disposeKillSwitch();
    globalShortcut.unregisterAll();
  });
}

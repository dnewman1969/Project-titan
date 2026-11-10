/**
 * Wires the game-view controller to one BrowserWindow: preview rectangle, move/resize,
 * and a close path that un-parents the game before the Electron HWND is destroyed
 * (an owned window is destroyed with its owner).
 */
import { screen, type BrowserWindow } from "electron";

import type { GameViewRect, GameViewStatus } from "../../shared/ipc";
import { hwndFromNativeHandle, scaleRect, viewportToScreenDip, type EmbedMode } from "./protocol";
import { GameViewController } from "./controller";
import { emergencyDetach, UnsupportedGameEmbedHost, Win32GameEmbedHost } from "./win32Host";

export interface GameViewBinding {
  controller: GameViewController;
}

function mapPreview(win: BrowserWindow, viewport: GameViewRect, mode: EmbedMode): GameViewRect | null {
  try {
    if (win.isDestroyed()) return null;
    if (mode === "dock") {
      const content = win.getContentBounds();
      const dip = viewportToScreenDip({ x: content.x, y: content.y }, viewport);
      return screen.dipToScreenRect(win, dip);
    }
    const display = screen.getDisplayMatching(win.getBounds());
    return scaleRect(viewport, display.scaleFactor);
  } catch {
    return null;
  }
}

export function bindGameView(win: BrowserWindow, send: (status: GameViewStatus) => void): GameViewBinding {
  const host = process.platform === "win32" ? new Win32GameEmbedHost() : new UnsupportedGameEmbedHost();
  const controller = new GameViewController({
    host,
    electronHwnd: () => {
      if (win.isDestroyed()) return null;
      return hwndFromNativeHandle(win.getNativeWindowHandle());
    },
    mapRect: (viewport, mode) => mapPreview(win, viewport, mode),
    contentHeight: () => {
      try {
        if (win.isDestroyed()) return 0;
        return win.getContentSize()[1] ?? 0;
      } catch {
        return 0;
      }
    },
  });
  controller.onStatus((status) => {
    const where = status.attached
      ? `${status.mode ?? "locked"} ${status.title ?? status.exe ?? ""}`
      : (status.reason ?? "");
    console.log(`[game-view] ${status.attached ? "attached" : "idle"} ${where}`.trim());
    send(status);
  });

  const reposition = () => {
    void controller.tick(false);
  };
  const discover = () => {
    void controller.tick(true);
  };
  win.on("move", reposition);
  win.on("resize", reposition);
  win.on("maximize", reposition);
  win.on("unmaximize", reposition);
  win.on("restore", () => {
    controller.setHold("minimized", false);
  });
  win.on("minimize", () => {
    controller.setHold("minimized", true);
  });
  win.on("show", discover);
  const timer = setInterval(discover, 400);

  let closing = false;
  win.on("close", (event) => {
    if (closing) return;
    event.preventDefault();
    closing = true;
    clearInterval(timer);
    void (async () => {
      try {
        const result = await controller.shutdown();
        if (!result.released && result.hwnd) emergencyDetach(result.hwnd);
      } finally {
        if (!win.isDestroyed()) win.close();
      }
    })();
  });

  discover();
  return { controller };
}

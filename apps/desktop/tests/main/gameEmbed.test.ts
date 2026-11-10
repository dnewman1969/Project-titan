// @vitest-environment node
import { describe, expect, it, vi } from "vitest";

import { GameViewController, type EmbedHost, type HostResult } from "../../src/main/gameEmbed/controller";
import {
  exeBase,
  hwndFromNativeHandle,
  initialMode,
  parseGameViewHold,
  parseGameViewRect,
  parseGameViewTarget,
  COVERING_CHROME_REASON,
  pickWindow,
  prefersDock,
  rectCoversSessionChrome,
  scaleRect,
  viewportToScreenDip,
  waitingReason,
  type FoundWindow,
  type ProbeResult,
} from "../../src/main/gameEmbed/protocol";

function windowOf(overrides: Partial<FoundWindow>): FoundWindow {
  return {
    hwnd: "1",
    pid: 10,
    title: "Kerbal Space Program",
    className: "UnityWndClass",
    exe: "E:\\SteamLibrary\\steamapps\\common\\Kerbal Space Program\\KSP_x64.exe",
    width: 1600,
    height: 900,
    ...overrides,
  };
}

class FakeHost implements EmbedHost {
  calls: string[] = [];
  windows: FoundWindow[] = [];
  probeResult: ProbeResult = {
    alive: true,
    parent: "0",
    owner: "100",
    visible: true,
    width: 800,
    height: 600,
  };
  failEmbed = false;
  released: string[] = [];
  shown: boolean[] = [];
  placed: string[] = [];

  available(): boolean {
    return true;
  }

  start(): Promise<void> {
    this.calls.push("start");
    return Promise.resolve();
  }

  find(): Promise<FoundWindow[]> {
    this.calls.push("find");
    return Promise.resolve(this.windows);
  }

  apply(request: {
    mode: string;
    hwnd: string;
    rect: { width: number; height: number };
  }): Promise<HostResult> {
    this.calls.push(`apply:${request.mode}:${request.hwnd}:${request.rect.width}x${request.rect.height}`);
    if (request.mode === "embed" && this.failEmbed)
      return Promise.resolve({ ok: false, error: "SetParent rejected" });
    return Promise.resolve({ ok: true, error: null });
  }

  place(request: {
    mode: string;
    rect: { x: number; y: number; width: number; height: number };
  }): Promise<HostResult> {
    this.placed.push(
      `${request.mode}:${request.rect.x},${request.rect.y},${request.rect.width}x${request.rect.height}`,
    );
    return Promise.resolve({ ok: true, error: null });
  }

  probe(): Promise<ProbeResult> {
    this.calls.push("probe");
    return Promise.resolve(this.probeResult);
  }

  setVisible(_hwnd: string, visible: boolean): Promise<HostResult> {
    this.shown.push(visible);
    return Promise.resolve({ ok: true, error: null });
  }

  release(hwnd: string): Promise<void> {
    this.released.push(hwnd);
    return Promise.resolve();
  }

  releaseAll(): Promise<void> {
    this.calls.push("releaseAll");
    return Promise.resolve();
  }

  focus(): Promise<void> {
    this.calls.push("focus");
    return Promise.resolve();
  }

  stop(): Promise<void> {
    this.calls.push("stop");
    return Promise.resolve();
  }
}

function controllerFor(host: FakeHost, now: () => number = () => 0): GameViewController {
  return new GameViewController({
    host,
    electronHwnd: () => "100",
    mapRect: (viewport, mode) => ({
      x: viewport.x + (mode === "dock" ? 50 : 0),
      y: viewport.y + 20,
      width: Math.round(viewport.width),
      height: Math.round(viewport.height),
    }),
    now,
    embedGraceMs: 500,
  });
}

describe("game window selection", () => {
  it("docks Unity and the known sims instead of reparenting them", () => {
    expect(prefersDock(windowOf({}))).toBe(true);
    expect(prefersDock(windowOf({ className: "Prism3D", exe: "C:\\Games\\eurotrucks2.exe" }))).toBe(true);
    expect(
      prefersDock(windowOf({ className: "Notepad", exe: "C:\\Windows\\notepad.exe", title: "Note" })),
    ).toBe(false);
    expect(initialMode(windowOf({}), "auto")).toBe("dock");
    expect(initialMode(windowOf({ className: "Notepad", exe: "C:\\Windows\\notepad.exe" }), "auto")).toBe(
      "embed",
    );
    expect(initialMode(windowOf({}), "embed")).toBe("embed");
  });

  it("prefers the launched pid, then the largest Unity window", () => {
    const small = windowOf({ hwnd: "1", pid: 4, width: 400, height: 300 });
    const large = windowOf({ hwnd: "2", pid: 9, width: 1920, height: 1080, title: "" });
    const other = windowOf({
      hwnd: "3",
      pid: 9,
      className: "Notepad",
      exe: "eurotrucks2.exe",
      width: 2000,
      height: 2000,
    });
    expect(pickWindow([small, large], 4)?.hwnd).toBe("1");
    expect(pickWindow([large, other], null)?.hwnd).toBe("2");
    expect(exeBase(large.exe)).toBe("ksp_x64.exe");
    expect(waitingReason("ksp")).toMatch(/Kerbal/);
  });

  it("maps the preview into screen DIP and physical child pixels", () => {
    expect(viewportToScreenDip({ x: 100, y: 40 }, { x: 8, y: 64, width: 900.2, height: 500.6 })).toEqual({
      x: 108,
      y: 104,
      width: 900,
      height: 501,
    });
    expect(scaleRect({ x: 10, y: 20, width: 100, height: 50 }, 1.5)).toEqual({
      x: 15,
      y: 30,
      width: 150,
      height: 75,
    });
    const handle = Buffer.alloc(8);
    handle.writeBigUInt64LE(4660n);
    expect(hwndFromNativeHandle(handle)).toBe("4660");
    expect(parseGameViewRect({ x: 1, y: 2, width: 3, height: 4 })).toEqual({
      x: 1,
      y: 2,
      width: 3,
      height: 4,
    });
    expect(parseGameViewRect({ x: Number.NaN, y: 0, width: 1, height: 1 })).toBeNull();
    expect(parseGameViewTarget({ gameSlug: "KSP", pid: 42 })).toEqual({ gameSlug: "ksp", pid: 42 });
    expect(parseGameViewTarget({ gameSlug: "nope", pid: 0 })).toEqual({ gameSlug: null, pid: null });
    expect(parseGameViewHold({ reason: "modal", on: true })).toEqual({ reason: "modal", on: true });
    expect(parseGameViewHold({ reason: "nodock", on: false })).toEqual({ reason: "nodock", on: false });
    expect(parseGameViewHold({ reason: "other", on: true })).toBeNull();
    expect(rectCoversSessionChrome({ x: 0, y: 0, width: 900, height: 980 }, 1000)).toBe(true);
    expect(rectCoversSessionChrome({ x: 8, y: 20, width: 800, height: 400 }, 1000)).toBe(true);
    expect(rectCoversSessionChrome({ x: 8, y: 80, width: 800, height: 700 }, 1000)).toBe(false);
    expect(rectCoversSessionChrome({ x: 8, y: 64, width: 1200, height: 1180 }, 1400)).toBe(false);
  });
});

describe("GameViewController", () => {
  it("docks KSP onto the preview and repositions it in screen space", async () => {
    const host = new FakeHost();
    host.windows = [windowOf({ hwnd: "77", pid: 4242 })];
    const view = controllerFor(host);
    view.setViewport({ x: 12, y: 30, width: 800, height: 600 });
    view.setTarget({ gameSlug: "ksp", pid: 4242 });
    await vi.waitFor(() => {
      expect(host.calls.some((call) => call.startsWith("apply:dock:77"))).toBe(true);
    });
    expect(host.calls.some((call) => call.startsWith("apply:embed"))).toBe(false);
    expect(view.currentStatus()).toMatchObject({
      attached: true,
      mode: "dock",
      pid: 4242,
      title: "Kerbal Space Program",
    });
    await view.tick(false);
    expect(host.placed.at(-1)).toBe("dock:62,50,800x600");
  });

  it("falls back to dock when SetParent does not keep the game as a child", async () => {
    let now = 0;
    const host = new FakeHost();
    host.windows = [
      windowOf({ hwnd: "9", className: "Notepad", exe: "C:\\Games\\custom.exe", title: "Custom", pid: 3 }),
    ];
    host.probeResult = { alive: true, parent: "0", owner: "0", visible: true, width: 10, height: 10 };
    const view = controllerFor(host, () => now);
    view.setViewport({ x: 0, y: 0, width: 640, height: 480 });
    await view.tick(true);
    expect(host.calls.some((call) => call.startsWith("apply:embed:9"))).toBe(true);
    now = 600;
    await view.tick(true);
    expect(host.released).toContain("9");
    expect(host.calls.some((call) => call.startsWith("apply:dock:9"))).toBe(true);
    expect(view.currentStatus().mode).toBe("dock");
  });

  it("hides the game while a modal hold is set and restores it afterwards", async () => {
    const host = new FakeHost();
    host.windows = [windowOf({ hwnd: "5" })];
    const view = controllerFor(host);
    view.setViewport({ x: 0, y: 0, width: 400, height: 300 });
    await view.tick(true);
    view.setHold("modal", true);
    await vi.waitFor(() => {
      expect(host.shown).toContain(false);
    });
    view.setHold("modal", false);
    await vi.waitFor(() => {
      expect(host.shown.at(-1)).toBe(true);
    });
  });

  it("searches again after the game window dies and releases it on shutdown", async () => {
    const host = new FakeHost();
    host.windows = [windowOf({ hwnd: "5" })];
    const view = controllerFor(host);
    view.setViewport({ x: 0, y: 0, width: 400, height: 300 });
    await view.tick(true);
    host.probeResult = { ...host.probeResult, alive: false };
    host.windows = [];
    await view.tick(true);
    expect(view.currentStatus().attached).toBe(false);
    const result = await view.shutdown();
    expect(result.released).toBe(true);
    expect(host.calls).toContain("releaseAll");
    expect(host.calls).toContain("stop");
  });

  it("does not dock a viewport that would cover the session chrome", async () => {
    const host = new FakeHost();
    host.windows = [windowOf({ hwnd: "77", pid: 4242 })];
    const view = new GameViewController({
      host,
      electronHwnd: () => "100",
      mapRect: (viewport) => viewport,
      contentHeight: () => 1000,
    });
    view.setViewport({ x: 0, y: 0, width: 900, height: 980 });
    view.setTarget({ gameSlug: "ksp", pid: 4242 });
    await view.tick(true);
    expect(host.calls.some((call) => call.startsWith("apply:"))).toBe(false);
    expect(view.currentStatus().attached).toBe(false);
    expect(view.currentStatus().reason).toBe(COVERING_CHROME_REASON);
    view.setViewport({ x: 8, y: 80, width: 800, height: 700 });
    await vi.waitFor(() => {
      expect(host.calls.some((call) => call.startsWith("apply:dock:77"))).toBe(true);
    });
  });

  it("does not move the game onto a tiny preview", async () => {
    const host = new FakeHost();
    host.windows = [windowOf({})];
    const view = controllerFor(host);
    view.setViewport({ x: 0, y: 0, width: 10, height: 10 });
    await view.tick(true);
    expect(host.calls.some((call) => call.startsWith("apply:"))).toBe(false);
    expect(view.currentStatus().reason).toBe("Waiting for the preview frame");
  });
});

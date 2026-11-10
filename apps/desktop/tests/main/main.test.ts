// @vitest-environment node
import type { ChildProcess, spawn, spawnSync } from "node:child_process";
import { EventEmitter } from "node:events";
import { relative, resolve, sep } from "node:path";

import type { MenuItemConstructorOptions } from "electron";
import { describe, expect, it, vi } from "vitest";

import { DEFAULT_KILL_HOTKEY, resolveMainConfig } from "../../src/main/config";
import { postKill, registerKillSwitch } from "../../src/main/killSwitch";
import { allowCapturePermission } from "../../src/main/permissions";
import { buildMenuTemplate } from "../../src/main/menu";
import {
  applyFirstPaintSwitches,
  describeAcceptedFeatures,
  firstPaintSwitches,
  layoutBump,
  nudgeCommittedLayout,
  revealWindow,
} from "../../src/main/firstPaint";
import {
  APP_INDEX_URL,
  APP_ORIGIN,
  clientFailureReaction,
  isAppUrl,
  mediaType,
  readRendererBody,
  resolveAppFile,
} from "../../src/main/navigation";
import {
  CrashBudget,
  startSupervisor,
  stopProcessTree,
  stopSupervisor,
  SupervisorClient,
  SupervisorMonitor,
} from "../../src/main/supervisor";
import { buildCsp, cspDirectives } from "../../src/shared/csp";
import type { SupervisorUpdate } from "../../src/shared/ipc";
import { findMenuItem, MENU } from "../../src/shared/menu";

function section(template: MenuItemConstructorOptions[], label: string): MenuItemConstructorOptions[] {
  const found = template.find((item) => item.label === label);
  if (!Array.isArray(found?.submenu)) throw new Error(`menu ${label} missing`);
  return found.submenu;
}

function item(items: MenuItemConstructorOptions[], id: string): MenuItemConstructorOptions {
  const found = items.find((i) => i.id === id);
  if (!found) throw new Error(`menu item ${id} missing`);
  return found;
}

function click(menuItem: MenuItemConstructorOptions): void {
  if (!menuItem.click) throw new Error("menu item has no click handler");
  (menuItem.click as () => void)();
}

describe("menu", () => {
  it("has the window menus in order", () => {
    expect(MENU.map((s) => s.label)).toEqual(["File", "Edit", "View", "AI", "Record", "Tools", "Help"]);
  });

  it("uses plain English labels and drops unfinished commands", () => {
    const labels = MENU.flatMap((s) => s.items.flatMap((i) => ("label" in i && i.label ? [i.label] : [])));
    expect(labels).toEqual([
      "New session",
      "Exit",
      "Crew",
      "Webcam",
      "Contract",
      "Telemetry",
      "Event log",
      "Game discovery",
      "Memory browser",
      "Start recording",
      "Stop recording",
      "Open recording folder",
      "Game discovery",
      "YouTube publish",
      "Logs",
      "Kill switch",
      "Documentation",
      "Beta test guide",
      "First-run setup",
      "kRPC and OBS",
      "About Titan",
    ]);
    for (const label of labels) {
      expect(label).not.toMatch(/M\d+\.T\d+/);
    }
    for (const removed of [
      "Open Session",
      "Replay Session",
      "Settings",
      "Personas",
      "Teams",
      "Control Bindings",
      "Blackboard Inspector",
      "Message Inspector",
      "Telemetry Charts",
      "Start Agents",
      "Stop Agents",
      "Models",
      "Director Report",
      "Add Marker",
      "Recording Settings",
      "Integration Installer",
      "Diagnostics Bundle",
      "Licenses",
    ]) {
      expect(labels).not.toContain(removed);
    }
    expect(findMenuItem("file.newSession")).toMatchObject({ accelerator: "CmdOrCtrl+N" });
    expect(findMenuItem("record.addMarker")).toBeUndefined();
  });

  it("builds an Electron template that routes clicks", () => {
    const send = vi.fn();
    const openDocs = vi.fn();
    const template = buildMenuTemplate({ send, openDocs }, { dev: false });
    const labels = template.flatMap((sectionItem) =>
      Array.isArray(sectionItem.submenu)
        ? sectionItem.submenu.flatMap((entry) => (typeof entry.label === "string" ? [entry.label] : []))
        : [],
    );
    expect(labels.some((label) => /M\d+\.T\d+/.test(label))).toBe(false);

    const view = section(template, "View");
    const crewToggle = item(view, "view.toggle.crew");
    expect(crewToggle).toMatchObject({ type: "checkbox", checked: true, label: "Crew" });
    click(crewToggle);
    expect(send).toHaveBeenCalledWith("view.toggle.crew");
    click(item(view, "view.gameDiscovery"));
    expect(send).toHaveBeenCalledWith("view.gameDiscovery");

    const tools = section(template, "Tools");
    click(item(tools, "tools.killSwitch"));
    expect(send).toHaveBeenCalledWith("tools.killSwitch");
    click(item(tools, "tools.logs"));
    expect(send).toHaveBeenCalledWith("tools.logs");

    const help = section(template, "Help");
    click(item(help, "help.docs"));
    expect(openDocs).toHaveBeenCalledOnce();
    expect(item(help, "help.krpcObs").label).toBe("kRPC and OBS");

    expect(section(template, "File").at(-1)).toEqual({ role: "quit", label: "Exit" });
    expect(view.some((i) => i.role === "toggleDevTools")).toBe(false);
  });

  it("adds developer tools only in dev", () => {
    const template = buildMenuTemplate({ send: vi.fn(), openDocs: vi.fn() }, { dev: true });
    expect(section(template, "View").some((i) => i.role === "toggleDevTools")).toBe(true);
  });
});

describe("config", () => {
  const base = { isPackaged: false, appPath: "/repo/apps/desktop", randomToken: () => "generated" };

  it("manages the API in development with a fresh token", () => {
    const cfg = resolveMainConfig({}, base);
    expect(cfg).toMatchObject({
      apiBase: "http://127.0.0.1:8765",
      supervisorBase: "http://127.0.0.1:8769",
      token: "generated",
      backend: "managed",
      killHotkey: DEFAULT_KILL_HOTKEY,
      repoRoot: resolve("/repo"),
    });
  });

  it("uses an external API when a launch token is provided", () => {
    const cfg = resolveMainConfig({ TITAN_LAUNCH_TOKEN: "abc", TITAN__API__PORT: "9000" }, base);
    expect(cfg).toMatchObject({ backend: "external", token: "abc", apiBase: "http://127.0.0.1:9000" });
  });

  it("starts no backend when packaged or disabled, and ignores bad ports", () => {
    expect(resolveMainConfig({}, { ...base, isPackaged: true }).backend).toBe("none");
    expect(resolveMainConfig({ TITAN_BACKEND: "none", TITAN__API__PORT: "99999" }, base)).toMatchObject({
      backend: "none",
      apiPort: 8765,
    });
  });

  it("generates distinct url-safe tokens by default", () => {
    const a = resolveMainConfig({}, { isPackaged: false, appPath: "/x/y" }).token;
    const b = resolveMainConfig({}, { isPackaged: false, appPath: "/x/y" }).token;
    expect(a).not.toBe(b);
    expect(a).toMatch(/^[A-Za-z0-9_-]{43}$/);
  });
});

describe("kill switch", () => {
  it("registers the hotkey and emits hotkey events", () => {
    let callback: (() => void) | undefined;
    const shortcuts = {
      register: vi.fn((_acc: string, cb: () => void) => {
        callback = cb;
        return true;
      }),
      unregister: vi.fn(),
    };
    const onKill = vi.fn();
    const reg = registerKillSwitch(
      shortcuts,
      "Ctrl+Shift+F12",
      onKill,
      () => new Date("2026-11-08T12:00:00Z"),
    );
    expect(reg.registered).toBe(true);
    callback?.();
    expect(onKill).toHaveBeenCalledWith({ source: "hotkey", at: "2026-11-08T12:00:00.000Z" });
    reg.dispose();
    expect(shortcuts.unregister).toHaveBeenCalledWith("Ctrl+Shift+F12");
  });

  it("does not unregister a hotkey it failed to register", () => {
    const shortcuts = { register: vi.fn(() => false), unregister: vi.fn() };
    registerKillSwitch(shortcuts, "Ctrl+Shift+F12", vi.fn()).dispose();
    expect(shortcuts.unregister).not.toHaveBeenCalled();
  });
});

class FakeChild extends EventEmitter {
  pid: number | undefined = 4242;
  exitCode: number | null = null;
  signalCode: NodeJS.Signals | null = null;
  stdout = new EventEmitter();
  stderr = new EventEmitter();
  kill = vi.fn(() => true);
}

describe("supervisor process", () => {
  it("runs titan-supervisor with the launch token, parent pid and ports", () => {
    const child = new FakeChild();
    const spawnFn = vi.fn((..._args: Parameters<typeof spawn>) => child as unknown as ChildProcess);
    const log = vi.fn<(line: string) => void>();
    startSupervisor({
      repoRoot: "/repo",
      token: "tok",
      apiPort: 8765,
      supervisorPort: 8769,
      corsOrigins: [APP_ORIGIN, "http://localhost:5173"],
      parentPid: 777,
      env: { PATH: "/bin" },
      log,
      spawnFn: spawnFn as unknown as typeof spawn,
    });
    const [command, args, options] = spawnFn.mock.calls[0] ?? [];
    expect(command).toBe("uv");
    expect(args).toEqual(["run", "titan-supervisor"]);
    expect(options).toMatchObject({
      cwd: "/repo",
      windowsHide: true,
      env: {
        PATH: "/bin",
        TITAN_LAUNCH_TOKEN: "tok",
        TITAN_PARENT_PID: "777",
        TITAN__API__PORT: "8765",
        TITAN__SUPERVISOR__PORT: "8769",
        TITAN__API__CORS_ORIGINS: '["app://titan","http://localhost:5173"]',
      },
    });
    child.stdout.emit("data", Buffer.from("[api] line one\nline two\n"));
    child.emit("error", new Error("ENOENT"));
    expect(log.mock.calls.map(([line]) => line)).toEqual([
      "[supervisor] [api] line one",
      "[supervisor] line two",
      "[supervisor] failed to start (is uv on PATH?): ENOENT",
    ]);
  });

  it("tree-kills on Windows and signals elsewhere", () => {
    const spawnSyncFn = vi.fn();
    const win = new FakeChild();
    stopProcessTree(win as unknown as ChildProcess, {
      platform: "win32",
      spawnSyncFn: spawnSyncFn as unknown as typeof spawnSync,
    });
    expect(spawnSyncFn).toHaveBeenCalledWith("taskkill", ["/pid", "4242", "/T", "/F"], { windowsHide: true });

    const posix = new FakeChild();
    stopProcessTree(posix as unknown as ChildProcess, { platform: "linux" });
    expect(posix.kill).toHaveBeenCalledWith("SIGTERM");

    const exited = new FakeChild();
    exited.exitCode = 0;
    stopProcessTree(exited as unknown as ChildProcess, { platform: "linux" });
    expect(exited.kill).not.toHaveBeenCalled();
  });

  it("stops gracefully through /shutdown when the supervisor exits in time", async () => {
    const child = new FakeChild();
    const client = {
      shutdown: vi.fn(() => {
        setTimeout(() => {
          child.exitCode = 0;
          child.emit("exit", 0, null);
        }, 5);
        return Promise.resolve(true);
      }),
    };
    expect(await stopSupervisor(child as unknown as ChildProcess, client, { platform: "linux" })).toBe(
      "graceful",
    );
    expect(child.kill).not.toHaveBeenCalled();
  });

  it("falls back to a tree kill when /shutdown fails or times out", async () => {
    const child = new FakeChild();
    child.kill = vi.fn(() => {
      child.signalCode = "SIGTERM";
      child.emit("exit", null, "SIGTERM");
      return true;
    });
    const client = { shutdown: vi.fn(() => Promise.resolve(false)) };
    expect(await stopSupervisor(child as unknown as ChildProcess, client, { platform: "linux" })).toBe(
      "forced",
    );
    expect(child.kill).toHaveBeenCalledWith("SIGTERM");

    const stuck = new FakeChild();
    const slow = { shutdown: vi.fn(() => Promise.resolve(true)) };
    const spawnSyncFn = vi.fn(() => {
      stuck.exitCode = 1;
      stuck.emit("exit", 1, null);
    });
    const result = await stopSupervisor(stuck as unknown as ChildProcess, slow, {
      timeoutMs: 10,
      platform: "win32",
      spawnSyncFn: spawnSyncFn as unknown as typeof spawnSync,
    });
    expect(result).toBe("forced");
    expect(spawnSyncFn).toHaveBeenCalledOnce();

    const gone = new FakeChild();
    gone.exitCode = 0;
    expect(await stopSupervisor(gone as unknown as ChildProcess, slow)).toBe("not-running");
  });

  it("allows three crash restarts per two minutes", () => {
    let now = 0;
    const budget = new CrashBudget(3, 120_000, () => now);
    expect([
      budget.allowRestart(),
      budget.allowRestart(),
      budget.allowRestart(),
      budget.allowRestart(),
    ]).toEqual([true, true, true, false]);
    now += 121_000;
    expect(budget.allowRestart()).toBe(true);
  });
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

describe("supervisor client and monitor", () => {
  const status = (events: { seq: number }[]) => ({
    started_at: "2026-11-08T12:00:00Z",
    ready: false,
    services: [{ name: "postgres", state: "starting" }],
    events,
  });

  it("sends the bearer token and asks only for new events", async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    let seqs = [{ seq: 1 }, { seq: 2 }];
    const fetchFn = vi.fn((url: string, init?: RequestInit) => {
      calls.push({ url, init });
      return Promise.resolve(jsonResponse(status(seqs)));
    });
    const updates: SupervisorUpdate[] = [];
    const monitor = new SupervisorMonitor(
      new SupervisorClient("http://127.0.0.1:8769", "tok", fetchFn),
      (u) => updates.push(u),
    );
    await monitor.poll();
    seqs = [{ seq: 3 }];
    await monitor.poll();
    expect(calls.map((c) => c.url)).toEqual([
      "http://127.0.0.1:8769/status?since=0",
      "http://127.0.0.1:8769/status?since=2",
    ]);
    expect(new Headers(calls[0]?.init?.headers).get("authorization")).toBe("Bearer tok");
    expect(updates.map((u) => u.process)).toEqual(["running", "running"]);
    expect((updates[1]?.status as { events: unknown[] }).events).toEqual([{ seq: 3 }]);
    const snapshot = monitor.snapshot();
    expect((snapshot.status as { events: unknown[] }).events).toEqual([{ seq: 1 }, { seq: 2 }, { seq: 3 }]);
  });

  it("stays quiet while the supervisor is not listening yet", async () => {
    const fetchFn = vi.fn(() => Promise.reject(new TypeError("fetch failed")));
    const onUpdate = vi.fn();
    const monitor = new SupervisorMonitor(
      new SupervisorClient("http://127.0.0.1:8769", "tok", fetchFn),
      onUpdate,
    );
    await monitor.poll();
    expect(onUpdate).not.toHaveBeenCalled();
    expect(monitor.snapshot()).toEqual({ process: "starting", detail: null, status: null });
    monitor.setProcess("exited", "gone");
    expect(onUpdate).toHaveBeenCalledWith({ process: "exited", detail: "gone", status: null });
  });

  it("reports whether /shutdown was accepted", async () => {
    const ok = new SupervisorClient("http://s", "t", () =>
      Promise.resolve(jsonResponse({ accepted: true }, 202)),
    );
    const down = new SupervisorClient("http://s", "t", () => Promise.reject(new Error("ECONNREFUSED")));
    expect(await ok.shutdown()).toBe(true);
    expect(await down.shutdown()).toBe(false);
  });
});

describe("kill switch API call", () => {
  it("POSTs /safety/kill with the token", async () => {
    const fetchFn = vi.fn((_url: string, _init?: RequestInit) => Promise.resolve(jsonResponse({}, 200)));
    expect(await postKill("http://127.0.0.1:8765", "tok", "hotkey", fetchFn)).toBe(200);
    const [url, init] = fetchFn.mock.calls[0] ?? [];
    expect(url).toBe("http://127.0.0.1:8765/api/v1/safety/kill");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe('{"source":"hotkey"}');
    expect(new Headers(init?.headers).get("authorization")).toBe("Bearer tok");
    const unreachable = await postKill("http://x", "t", "hotkey", () => Promise.reject(new Error("refused")));
    expect(unreachable).toBe("refused");
  });
});

describe("navigation guard", () => {
  it("allows only the app's own renderer", () => {
    expect(isAppUrl("http://localhost:5173/", "http://localhost:5173")).toBe(true);
    expect(isAppUrl("http://localhost:5174/", "http://localhost:5173")).toBe(false);
    expect(isAppUrl("app://titan/index.html", undefined)).toBe(true);
    expect(isAppUrl("app://evil/index.html", undefined)).toBe(false);
    expect(isAppUrl("file:///C:/Titan/resources/app.asar/out/renderer/index.html", undefined)).toBe(false);
    expect(isAppUrl("https://example.com/", undefined)).toBe(false);
    expect(isAppUrl("not a url", undefined)).toBe(false);
    expect(isAppUrl(undefined, undefined)).toBe(false);
  });
});

describe("Windows first paint", () => {
  it("requests the occlusion switches and reports when Chromium did not accept them", () => {
    expect(firstPaintSwitches("win32")).toEqual([
      { switchName: "disable-features", value: "CalculateNativeWinOcclusion,WidgetLayering" },
    ]);
    expect(firstPaintSwitches("linux")).toEqual([]);
    const applied: string[] = [];
    applyFirstPaintSwitches(
      {
        appendSwitch(name, value) {
          applied.push(`${name}=${value ?? ""}`);
        },
      },
      "win32",
    );
    expect(applied).toEqual(["disable-features=CalculateNativeWinOcclusion,WidgetLayering"]);
    expect(describeAcceptedFeatures("")).toContain("missing=CalculateNativeWinOcclusion,WidgetLayering");
    expect(describeAcceptedFeatures("CalculateNativeWinOcclusion,WidgetLayering")).toContain("missing=none");
  });

  it("shows the window on ready-to-show without resizing the blank frame", () => {
    const sizes: [number, number][] = [];
    let shown = 0;
    const win = {
      show() {
        shown += 1;
      },
      getSize: () => [1600, 1000] as const,
      setSize(width: number, height: number) {
        sizes.push([width, height]);
      },
    };
    revealWindow(win, "win32");
    revealWindow(win, "linux");
    expect(shown).toBe(2);
    expect(sizes).toEqual([]);
  });

  it("nudges layout only after a commit, waits between sizes, and skips setSize while maximized", async () => {
    expect(layoutBump(1)).toBe(2);
    expect(layoutBump(1.75)).toBe(2);
    expect(layoutBump(2.5)).toBe(3);
    const sizes: [number, number][] = [];
    const waits: string[] = [];
    const resized = await nudgeCommittedLayout(
      {
        isMaximized: () => false,
        getSize: () => [1600, 1000],
        setSize(width, height) {
          sizes.push([width, height]);
        },
        invalidateClient() {
          throw new Error("not maximized");
        },
      },
      "win32",
      1.75,
      () => {
        waits.push("resize");
        return Promise.resolve();
      },
    );
    expect(resized).toBe("resized");
    expect(waits).toEqual(["resize"]);
    expect(sizes).toEqual([
      [1600, 1002],
      [1600, 1000],
    ]);
    const skipped = await nudgeCommittedLayout(
      {
        isMaximized: () => false,
        getSize: () => [0, 0],
        setSize() {
          throw new Error("no size");
        },
        invalidateClient() {
          throw new Error("no size");
        },
      },
      "win32",
      1,
      () => Promise.resolve(),
    );
    expect(skipped).toBe("skipped");
    let invalidated = 0;
    const maximized = await nudgeCommittedLayout(
      {
        isMaximized: () => true,
        getSize: () => [1600, 1000],
        setSize() {
          throw new Error("maximized");
        },
        invalidateClient() {
          invalidated += 1;
        },
      },
      "win32",
      1.5,
      () => Promise.reject(new Error("no resize")),
    );
    expect(maximized).toBe("invalidated");
    expect(invalidated).toBe(1);
    expect(
      await nudgeCommittedLayout(
        {
          isMaximized: () => false,
          getSize: () => [1600, 1000],
          setSize() {
            throw new Error("linux");
          },
          invalidateClient() {
            throw new Error("linux");
          },
        },
        "linux",
        1,
        () => Promise.resolve(),
      ),
    ).toBe("skipped");
  });

  it("uses one failure page for the dev server and for a bad app:// load", () => {
    const dev = clientFailureReaction({
      kind: "did-fail-load",
      errorCode: -105,
      isMainFrame: true,
      url: "http://localhost:5173/",
      description: "ERR_NAME_NOT_RESOLVED",
      reloadUrl: "http://localhost:5173/",
    });
    expect(dev).toContain("data:text/html");
    const devHtml = decodeURIComponent(dev?.slice("data:text/html;charset=utf-8,".length) ?? "");
    expect(devHtml).toContain("PROGRAM");
    expect(devHtml).toContain("-105");
    expect(devHtml).toContain("Reload");
    expect(devHtml).toContain("http://localhost:5173/");
    expect(
      clientFailureReaction({
        kind: "did-fail-load",
        errorCode: -3,
        isMainFrame: true,
        url: "http://localhost:5173/",
        description: "ERR_ABORTED",
        reloadUrl: "http://localhost:5173/",
      }),
    ).toBeNull();
    const crashed = clientFailureReaction({
      kind: "render-process-gone",
      description: "crashed",
      reloadUrl: APP_INDEX_URL,
    });
    const crashedHtml = decodeURIComponent(crashed?.slice("data:text/html;charset=utf-8,".length) ?? "");
    expect(crashedHtml).toContain("renderer-gone");
    expect(crashedHtml).toContain(APP_INDEX_URL);
    expect(crashedHtml).toContain("PROGRAM");
  });
});

describe("renderer route", () => {
  it("serves the script with a javascript type and turns a missing file into 404", async () => {
    expect(mediaType("index.html")).toBe("text/html; charset=utf-8");
    expect(mediaType("assets/index-abc.js")).toBe("text/javascript; charset=utf-8");
    const page = await readRendererBody("index.html", () => Promise.resolve(new Uint8Array([60, 112, 62])));
    expect(page.status).toBe(200);
    expect(page.headers.get("content-type")).toBe("text/html; charset=utf-8");
    expect(new TextDecoder().decode(await page.arrayBuffer())).toBe("<p>");
    const missing = await readRendererBody("missing.png", () => Promise.reject(new Error("ENOENT")));
    expect(missing.status).toBe(404);
  });
});

describe("app:// file resolution", () => {
  const root = resolve("/opt/titan/out/renderer");

  it("maps app URLs inside the renderer folder", () => {
    expect(resolveAppFile(root, "app://titan/")).toBe(resolve(root, "index.html"));
    expect(resolveAppFile(root, "app://titan/assets/index-1.js")).toBe(resolve(root, "assets/index-1.js"));
    expect(resolveAppFile(root, "app://titan/a%20b.css")).toBe(resolve(root, "a b.css"));
  });

  it("never resolves outside the renderer folder", () => {
    for (const url of [
      "app://titan/../secret.txt",
      "app://titan/%2e%2e/%2e%2e/etc/passwd",
      "app://titan/..%5c..%5cwindows",
      "app://titan/assets/..%2f..%2f..%2fsecret",
    ]) {
      const file = resolveAppFile(root, url);
      expect(file === null || (file.startsWith(root + sep) && !relative(root, file).startsWith(".."))).toBe(
        true,
      );
    }
  });

  it("rejects foreign hosts and malformed escapes", () => {
    expect(resolveAppFile(root, "app://other/index.html")).toBeNull();
    expect(resolveAppFile(root, "https://titan/index.html")).toBeNull();
    expect(resolveAppFile(root, "app://titan/%E0%A4%A")).toBeNull();
  });
});

describe("capture permissions", () => {
  it("allows the webcam and microphone and denies everything else", () => {
    expect(allowCapturePermission("media")).toBe(true);
    expect(allowCapturePermission("display-capture")).toBe(false);
    expect(allowCapturePermission("geolocation")).toBe(false);
  });
});

describe("CSP", () => {
  it("matches Section 9.6 in production", () => {
    const d = cspDirectives({ dev: false });
    expect(d["default-src"]).toEqual(["'self'"]);
    expect(d["script-src"]).toEqual(["'self'"]);
    expect(d["connect-src"]).toEqual([
      "http://127.0.0.1:8765",
      "ws://127.0.0.1:8765",
      "http://127.0.0.1:8767",
      "http://127.0.0.1:8790",
    ]);
    expect(d["img-src"]).toEqual([
      "'self'",
      "data:",
      "blob:",
      "http://127.0.0.1:8767",
      "http://127.0.0.1:8188",
    ]);
    expect(d["media-src"]).toEqual(["'self'", "blob:", "http://127.0.0.1:8767"]);
    expect(buildCsp({ dev: false })).not.toContain("localhost");
  });

  it("relaxes only what the Vite dev server needs in development", () => {
    const csp = buildCsp({ dev: true, apiPort: 9000 });
    expect(csp).toContain("script-src 'self' 'unsafe-inline'");
    expect(csp).toContain("ws://localhost:*");
    expect(csp).toContain("http://127.0.0.1:9000");
  });
});

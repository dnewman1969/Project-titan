// @vitest-environment node
import type { ChildProcess, spawn, spawnSync } from "node:child_process";
import { EventEmitter } from "node:events";
import { relative, resolve, sep } from "node:path";

import type { MenuItemConstructorOptions } from "electron";
import { describe, expect, it, vi } from "vitest";

import { DEFAULT_KILL_HOTKEY, resolveMainConfig } from "../../src/main/config";
import { postKill, registerKillSwitch } from "../../src/main/killSwitch";
import { buildMenuTemplate } from "../../src/main/menu";
import { APP_ORIGIN, isAppUrl, resolveAppFile } from "../../src/main/navigation";
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
  it("has the Section 2.13 menus in order", () => {
    expect(MENU.map((s) => s.label)).toEqual(["FILE", "EDIT", "VIEW", "AI", "RECORD", "TOOLS", "HELP"]);
  });

  it("contains every spec menu item", () => {
    const labels = MENU.flatMap((s) => s.items.flatMap((i) => ("label" in i && i.label ? [i.label] : [])));
    for (const label of [
      "New Session",
      "Open Session",
      "Replay Session",
      "Settings",
      "Exit",
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
      "Memory Browser",
      "Start Recording",
      "Stop Recording",
      "Add Marker",
      "Recording Settings",
      "Open Folder",
      "Game Discovery",
      "YouTube Publish",
      "Integration Installer",
      "Logs",
      "Diagnostics Bundle",
      "Documentation",
      "About Titan",
      "Licenses",
    ]) {
      expect(labels).toContain(label);
    }
    expect(findMenuItem("record.addMarker")).toMatchObject({ accelerator: "CmdOrCtrl+M" });
  });

  it("builds an Electron template that routes clicks", () => {
    const send = vi.fn();
    const openDocs = vi.fn();
    const template = buildMenuTemplate({ send, openDocs }, { dev: false });
    const view = section(template, "VIEW");
    const agentsToggle = item(view, "view.toggle.agents");
    expect(agentsToggle).toMatchObject({ type: "checkbox", checked: true });
    click(agentsToggle);
    expect(send).toHaveBeenCalledWith("view.toggle.agents");
    click(item(view, "view.blackboardInspector"));
    expect(send).toHaveBeenCalledWith("view.blackboardInspector");

    const help = section(template, "HELP");
    click(item(help, "help.docs"));
    expect(openDocs).toHaveBeenCalledOnce();
    expect(item(help, "help.licenses").label).toBe("Licenses  (M10.T4)");

    expect(section(template, "FILE").at(-1)).toEqual({ role: "quit", label: "Exit" });
    expect(view.some((i) => i.role === "toggleDevTools")).toBe(false);
  });

  it("adds developer tools only in dev", () => {
    const template = buildMenuTemplate({ send: vi.fn(), openDocs: vi.fn() }, { dev: true });
    expect(section(template, "VIEW").some((i) => i.role === "toggleDevTools")).toBe(true);
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

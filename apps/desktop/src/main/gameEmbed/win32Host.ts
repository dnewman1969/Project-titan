/**
 * Win32 game-window host. Electron's asar fuse forbids unpacked native addons, so the
 * User32 calls run in a long-lived Windows PowerShell process (DPI-aware) speaking JSON lines.
 * Linux and tests never start it.
 */
import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import type { GameViewRect } from "../../shared/ipc";
import type { ApplyRequest, EmbedHost, HostResult, PlaceRequest } from "./controller";
import type { FoundWindow, ProbeResult } from "./protocol";
import hostSource from "./host.ps1?raw";

const DETACH_SCRIPT = `
param([Parameter(Mandatory = $true)][long]$Hwnd)
$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public class TitanDetach {
  [DllImport("user32.dll")] public static extern IntPtr SetParent(IntPtr child, IntPtr parent);
  [DllImport("user32.dll")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr value);
  [DllImport("user32.dll", EntryPoint = "SetWindowLongPtrW")] public static extern IntPtr SetWindowLongPtr(IntPtr hWnd, int nIndex, IntPtr value);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr insertAfter, int x, int y, int cx, int cy, uint flags);
  public static void Go(long raw) {
    try { SetThreadDpiAwarenessContext(new System.IntPtr(-4)); } catch { }
    System.IntPtr hwnd = new System.IntPtr(raw);
    SetParent(hwnd, System.IntPtr.Zero);
    SetWindowLongPtr(hwnd, -16, new System.IntPtr(0x80000000L | 0x10000000L | 0x04000000L));
    SetWindowLongPtr(hwnd, -8, System.IntPtr.Zero);
    SetWindowPos(hwnd, System.IntPtr.Zero, 80, 80, 1280, 720, 0x0040 | 0x0020);
  }
}
'@
[TitanDetach]::Go($Hwnd)
`;

interface HostReply {
  id?: number;
  ok?: boolean;
  op?: string;
  error?: string;
  windows?: unknown;
  alive?: boolean;
  parent?: string;
  owner?: string;
  visible?: boolean;
  width?: number;
  height?: number;
}

interface Waiter {
  resolve: (reply: HostReply) => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}

function powershellExe(): string {
  const root = process.env.SystemRoot || "C:\\Windows";
  return join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe");
}

function asWindows(value: unknown): FoundWindow[] {
  const rows = Array.isArray(value) ? value : value && typeof value === "object" ? [value] : [];
  const found: FoundWindow[] = [];
  for (const item of rows) {
    if (typeof item !== "object" || item === null) continue;
    const row = item as Record<string, unknown>;
    if (typeof row.hwnd !== "string" || typeof row.pid !== "number") continue;
    found.push({
      hwnd: row.hwnd,
      pid: row.pid,
      title: typeof row.title === "string" ? row.title : "",
      className: typeof row.className === "string" ? row.className : "",
      exe: typeof row.exe === "string" ? row.exe : "",
      width: typeof row.width === "number" ? row.width : 0,
      height: typeof row.height === "number" ? row.height : 0,
    });
  }
  return found;
}

function resultOf(reply: HostReply): HostResult {
  if (reply.ok === true) return { ok: true, error: null };
  return { ok: false, error: reply.error && reply.error.length > 0 ? reply.error : "game view host failed" };
}

/** Last-resort unparent if the long-lived host does not answer before Titan exits. */
export function emergencyDetach(hwnd: string): void {
  if (process.platform !== "win32") return;
  if (!/^\d+$/.test(hwnd) || hwnd === "0") return;
  const scriptPath = join(tmpdir(), "titan-game-embed-detach.ps1");
  writeFileSync(scriptPath, DETACH_SCRIPT, "utf8");
  spawnSync(
    powershellExe(),
    ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", scriptPath, hwnd],
    {
      windowsHide: true,
      timeout: 4000,
    },
  );
}

export class Win32GameEmbedHost implements EmbedHost {
  private proc: ChildProcess | null = null;
  private stdout = "";
  private stderr = "";
  private ready: Promise<void> | null = null;
  private failed: string | null = null;
  private nextId = 1;
  private readonly pending = new Map<number, Waiter>();
  private chain: Promise<void> = Promise.resolve();

  available(): boolean {
    return process.platform === "win32" && this.failed === null;
  }

  start(): Promise<void> {
    if (process.platform !== "win32") return Promise.resolve();
    if (this.ready) return this.ready;
    this.ready = this.spawn();
    return this.ready;
  }

  find(exes: string[]): Promise<FoundWindow[]> {
    return this.call({ op: "find", exes: exes.join(","), minWidth: 200, minHeight: 150 }).then((reply) =>
      asWindows(reply.windows),
    );
  }

  apply(request: ApplyRequest): Promise<HostResult> {
    return this.call({
      op: request.mode === "embed" ? "embed" : "dock",
      hwnd: request.hwnd,
      anchor: request.anchor,
      x: request.rect.x,
      y: request.rect.y,
      width: request.rect.width,
      height: request.rect.height,
    }).then(resultOf);
  }

  place(request: PlaceRequest): Promise<HostResult> {
    return this.call(rectBody("place", request.hwnd, request.anchor, request.rect, request.mode)).then(
      resultOf,
    );
  }

  probe(hwnd: string): Promise<ProbeResult> {
    return this.call({ op: "probe", hwnd }).then((reply) => ({
      alive: reply.alive === true,
      parent: reply.parent ?? "0",
      owner: reply.owner ?? "0",
      visible: reply.visible === true,
      width: typeof reply.width === "number" ? reply.width : 0,
      height: typeof reply.height === "number" ? reply.height : 0,
    }));
  }

  setVisible(hwnd: string, visible: boolean): Promise<HostResult> {
    return this.call({ op: "visible", hwnd, show: visible }).then(resultOf);
  }

  async release(hwnd: string): Promise<void> {
    await this.call({ op: "release", hwnd }).then(resultOf);
  }

  async releaseAll(): Promise<void> {
    await this.call({ op: "releaseAll" }).then(resultOf);
  }

  async focus(hwnd: string): Promise<void> {
    await this.call({ op: "focus", hwnd }).then(resultOf);
  }

  async stop(): Promise<void> {
    await this.chain.catch(() => undefined);
    const proc = this.proc;
    this.proc = null;
    if (!proc) return;
    try {
      proc.stdin?.end();
    } catch {
      /* pipe already closed */
    }
    await new Promise<void>((resolve) => {
      const timer = setTimeout(() => {
        proc.kill();
        resolve();
      }, 800);
      proc.once("exit", () => {
        clearTimeout(timer);
        resolve();
      });
    });
  }

  private call(body: Record<string, unknown>): Promise<HostReply> {
    const id = this.nextId;
    this.nextId += 1;
    const run = async (): Promise<HostReply> => {
      await this.start();
      if (this.failed || !this.proc?.stdin) throw new Error(this.failed ?? "game view host stopped");
      return await new Promise<HostReply>((resolve, reject) => {
        const timer = setTimeout(() => {
          this.pending.delete(id);
          reject(new Error("game view host timed out"));
        }, 5000);
        this.pending.set(id, { resolve, reject, timer });
        this.proc?.stdin?.write(`${JSON.stringify({ id, ...body })}\n`, (error) => {
          if (!error) return;
          clearTimeout(timer);
          this.pending.delete(id);
          reject(error);
        });
      });
    };
    const result = this.chain.then(run, run);
    this.chain = result.then(
      () => undefined,
      () => undefined,
    );
    return result;
  }

  private spawn(): Promise<void> {
    const scriptPath = join(tmpdir(), "titan-game-embed-host.ps1");
    writeFileSync(scriptPath, hostSource, "utf8");
    const proc = spawn(
      powershellExe(),
      ["-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", scriptPath],
      { windowsHide: true, stdio: ["pipe", "pipe", "pipe"] },
    );
    this.proc = proc;
    return new Promise<void>((resolve, reject) => {
      let settled = false;
      const rejectPending = (message: string) => {
        this.failed = message;
        for (const [id, waiter] of this.pending) {
          clearTimeout(waiter.timer);
          waiter.reject(new Error(message));
          this.pending.delete(id);
        }
      };
      const failStart = (message: string) => {
        rejectPending(message);
        if (settled) return;
        settled = true;
        reject(new Error(message));
      };
      proc.stdout.setEncoding("utf8");
      proc.stdout.on("data", (chunk: string) => {
        this.stdout += chunk;
        let newline = this.stdout.indexOf("\n");
        while (newline >= 0) {
          const line = this.stdout.slice(0, newline).replace(/\r$/, "").trim();
          this.stdout = this.stdout.slice(newline + 1);
          newline = this.stdout.indexOf("\n");
          if (!line) continue;
          this.onLine(
            line,
            () => {
              if (settled) return;
              settled = true;
              resolve();
            },
            failStart,
          );
        }
      });
      proc.stderr.setEncoding("utf8");
      proc.stderr.on("data", (chunk: string) => {
        this.stderr = (this.stderr + chunk).slice(-2000);
      });
      proc.on("error", (error) => {
        failStart(error.message);
      });
      proc.on("exit", (code) => {
        const message = this.stderr.trim() || `game view host exited (${String(code)})`;
        failStart(message);
      });
    });
  }

  private onLine(line: string, onReady: () => void, onFail: (message: string) => void): void {
    let reply: HostReply;
    try {
      reply = JSON.parse(line) as HostReply;
    } catch {
      return;
    }
    if (reply.op === "ready") {
      if (reply.ok === false) onFail(reply.error ?? "game view host failed to start");
      else onReady();
      return;
    }
    if (typeof reply.id !== "number") return;
    const waiter = this.pending.get(reply.id);
    if (!waiter) return;
    clearTimeout(waiter.timer);
    this.pending.delete(reply.id);
    waiter.resolve(reply);
  }
}

function rectBody(
  op: string,
  hwnd: string,
  anchor: string,
  rect: GameViewRect,
  mode?: string,
): Record<string, unknown> {
  return {
    op,
    hwnd,
    anchor,
    mode,
    x: rect.x,
    y: rect.y,
    width: rect.width,
    height: rect.height,
  };
}

export class UnsupportedGameEmbedHost implements EmbedHost {
  available(): boolean {
    return false;
  }

  start(): Promise<void> {
    return Promise.resolve();
  }

  find(): Promise<FoundWindow[]> {
    return Promise.resolve([]);
  }

  apply(): Promise<HostResult> {
    return Promise.resolve({ ok: false, error: "Game embedding runs on Windows" });
  }

  place(): Promise<HostResult> {
    return Promise.resolve({ ok: false, error: "Game embedding runs on Windows" });
  }

  probe(): Promise<ProbeResult> {
    return Promise.resolve({ alive: false, parent: "0", owner: "0", visible: false, width: 0, height: 0 });
  }

  setVisible(): Promise<HostResult> {
    return Promise.resolve({ ok: false, error: "Game embedding runs on Windows" });
  }

  release(): Promise<void> {
    return Promise.resolve();
  }

  releaseAll(): Promise<void> {
    return Promise.resolve();
  }

  focus(): Promise<void> {
    return Promise.resolve();
  }

  stop(): Promise<void> {
    return Promise.resolve();
  }
}

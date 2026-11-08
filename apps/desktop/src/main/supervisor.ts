/**
 * titan-supervisor lifecycle (Sections 2.2 and 2.3, M1.T5). Electron main starts the supervisor
 * with the launch token, polls its internal API for the boot splash, and on quit asks it to stop
 * everything in order before falling back to a tree kill. The supervisor also exits by itself when
 * this process dies (`TITAN_PARENT_PID`), and on Windows its job object takes every child with it.
 */
import { spawn, spawnSync, type ChildProcess } from "node:child_process";

import type { SupervisorProcessState, SupervisorUpdate } from "../shared/ipc";
import { LAUNCH_TOKEN_ENV } from "./config";

export const PARENT_PID_ENV = "TITAN_PARENT_PID";
export const GRACEFUL_STOP_MS = 20_000;
export const MAX_EVENTS = 200;

export interface SupervisorOptions {
  repoRoot: string;
  token: string;
  apiPort: number;
  supervisorPort: number;
  /** Renderer origins the API must allow (`api.cors_origins`). */
  corsOrigins: string[];
  parentPid?: number;
  env?: NodeJS.ProcessEnv;
  log?: (line: string) => void;
  spawnFn?: typeof spawn;
}

export function startSupervisor({
  repoRoot,
  token,
  apiPort,
  supervisorPort,
  corsOrigins,
  parentPid = process.pid,
  env = process.env,
  log = console.log,
  spawnFn = spawn,
}: SupervisorOptions): ChildProcess {
  const child = spawnFn("uv", ["run", "titan-supervisor"], {
    cwd: repoRoot,
    env: {
      ...env,
      [LAUNCH_TOKEN_ENV]: token,
      [PARENT_PID_ENV]: String(parentPid),
      TITAN__API__PORT: String(apiPort),
      TITAN__API__CORS_ORIGINS: JSON.stringify(corsOrigins),
      TITAN__SUPERVISOR__PORT: String(supervisorPort),
      PYTHONUNBUFFERED: "1",
    },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
  const forward = (chunk: Buffer) => {
    for (const line of chunk.toString("utf8").split(/\r?\n/)) if (line) log(`[supervisor] ${line}`);
  };
  child.stdout.on("data", forward);
  child.stderr.on("data", forward);
  child.on("error", (err) => {
    log(`[supervisor] failed to start (is uv on PATH?): ${err.message}`);
  });
  return child;
}

type FetchFn = (input: string, init?: RequestInit) => Promise<Response>;

/** Client for the supervisor's internal API on 127.0.0.1 (Section 5.2, "Supervisor RPC"). */
export class SupervisorClient {
  constructor(
    readonly baseUrl: string,
    private readonly token: string,
    private readonly fetchFn: FetchFn = fetch,
    private readonly timeoutMs = 1500,
  ) {}

  private request(path: string, method = "GET"): Promise<Response> {
    return this.fetchFn(`${this.baseUrl}${path}`, {
      method,
      headers: { Authorization: `Bearer ${this.token}` },
      signal: AbortSignal.timeout(this.timeoutMs),
    });
  }

  /** Raw `SupervisorStatus` JSON; the renderer validates it against the generated schema. */
  async status(since = 0): Promise<unknown> {
    const response = await this.request(`/status?since=${since}`);
    if (!response.ok) throw new Error(`supervisor /status answered ${response.status}`);
    return response.json();
  }

  async shutdown(): Promise<boolean> {
    try {
      return (await this.request("/shutdown", "POST")).ok;
    } catch {
      return false;
    }
  }
}

function eventsOf(status: unknown): { seq: number }[] {
  if (typeof status !== "object" || status === null) return [];
  const events = (status as { events?: unknown }).events;
  if (!Array.isArray(events)) return [];
  return events.filter(
    (e): e is { seq: number } =>
      typeof e === "object" && e !== null && typeof (e as { seq?: unknown }).seq === "number",
  );
}

/**
 * Polls `/status?since=<last seq>` and keeps a full snapshot (status plus the last MAX_EVENTS
 * events), so a renderer that loads late, or reloads, still sees how the boot went.
 */
export class SupervisorMonitor {
  private lastSeq = 0;
  private events: unknown[] = [];
  private latest: unknown = null;
  private process: SupervisorProcessState = "starting";
  private detail: string | null = null;
  private timer: NodeJS.Timeout | null = null;
  private polling = false;

  constructor(
    private readonly client: SupervisorClient,
    private readonly onUpdate: (update: SupervisorUpdate) => void,
    private readonly intervalMs = 1000,
  ) {}

  snapshot(): SupervisorUpdate {
    const status =
      this.latest === null ? null : { ...(this.latest as Record<string, unknown>), events: [...this.events] };
    return { process: this.process, detail: this.detail, status };
  }

  setProcess(state: SupervisorProcessState, detail: string | null = null): void {
    this.process = state;
    this.detail = detail;
    this.onUpdate(this.snapshot());
  }

  start(): void {
    if (this.timer) return;
    void this.poll();
    this.timer = setInterval(() => void this.poll(), this.intervalMs);
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }

  async poll(): Promise<void> {
    if (this.polling) return;
    this.polling = true;
    try {
      const status = await this.client.status(this.lastSeq);
      const fresh = eventsOf(status).filter((e) => e.seq > this.lastSeq);
      if (fresh.length) {
        this.lastSeq = Math.max(...fresh.map((e) => e.seq));
        this.events = [...this.events, ...fresh].slice(-MAX_EVENTS);
      }
      this.latest = status;
      if (this.process === "starting") this.process = "running";
      this.onUpdate({ ...this.snapshot(), status: { ...(status as object), events: fresh } });
    } catch {
      // Not listening yet (booting) or gone; the process exit handler reports the latter.
    } finally {
      this.polling = false;
    }
  }
}

export function waitForExit(child: ChildProcess, timeoutMs: number): Promise<boolean> {
  if (child.exitCode !== null || child.signalCode !== null) return Promise.resolve(true);
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      child.off("exit", onExit);
      resolve(false);
    }, timeoutMs);
    const onExit = () => {
      clearTimeout(timer);
      resolve(true);
    };
    child.once("exit", onExit);
  });
}

export interface StopOptions {
  platform?: NodeJS.Platform;
  spawnSyncFn?: typeof spawnSync;
}

/** `uv run` starts Python as a child, so Windows needs a tree kill; elsewhere uv forwards SIGTERM. */
export function stopProcessTree(
  child: ChildProcess,
  { platform = process.platform, spawnSyncFn = spawnSync }: StopOptions = {},
): void {
  if (child.exitCode !== null || child.signalCode !== null || child.pid === undefined) return;
  if (platform === "win32") {
    spawnSyncFn("taskkill", ["/pid", String(child.pid), "/T", "/F"], { windowsHide: true });
  } else {
    child.kill("SIGTERM");
  }
}

export type StopResult = "not-running" | "graceful" | "forced";

/** Ask the supervisor to stop everything in reverse start order; tree-kill it if it does not. */
export async function stopSupervisor(
  child: ChildProcess,
  client: Pick<SupervisorClient, "shutdown">,
  { timeoutMs = GRACEFUL_STOP_MS, ...stop }: StopOptions & { timeoutMs?: number } = {},
): Promise<StopResult> {
  if (child.exitCode !== null || child.signalCode !== null) return "not-running";
  if ((await client.shutdown()) && (await waitForExit(child, timeoutMs))) return "graceful";
  stopProcessTree(child, stop);
  await waitForExit(child, 5000);
  return "forced";
}

/** Restart a crashed supervisor at most `max` times per `windowMs` (Section 2.3: "Restarted by Electron"). */
export class CrashBudget {
  private crashes: number[] = [];

  constructor(
    private readonly max = 3,
    private readonly windowMs = 120_000,
    private readonly now: () => number = Date.now,
  ) {}

  allowRestart(): boolean {
    const t = this.now();
    this.crashes = [...this.crashes.filter((c) => t - c < this.windowMs), t];
    return this.crashes.length <= this.max;
  }
}

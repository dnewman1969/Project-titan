/**
 * Backend process management. Until titan-supervisor exists (M1.T3, wired here in M1.T5), the
 * development shell starts the API directly with the launch token and kills its process tree on quit.
 */
import { spawn, spawnSync, type ChildProcess } from "node:child_process";

import { LAUNCH_TOKEN_ENV } from "./config";

export interface ManagedApiOptions {
  repoRoot: string;
  token: string;
  apiPort: number;
  /** Renderer origins the API must allow (`api.cors_origins`). */
  corsOrigins: string[];
  env?: NodeJS.ProcessEnv;
  log?: (line: string) => void;
  spawnFn?: typeof spawn;
}

export function startManagedApi({
  repoRoot,
  token,
  apiPort,
  corsOrigins,
  env = process.env,
  log = console.log,
  spawnFn = spawn,
}: ManagedApiOptions): ChildProcess {
  const child = spawnFn("uv", ["run", "titan-api"], {
    cwd: repoRoot,
    env: {
      ...env,
      [LAUNCH_TOKEN_ENV]: token,
      TITAN__API__PORT: String(apiPort),
      TITAN__API__CORS_ORIGINS: JSON.stringify(corsOrigins),
      PYTHONUNBUFFERED: "1",
    },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });
  const forward = (chunk: Buffer) => {
    for (const line of chunk.toString("utf8").split(/\r?\n/)) if (line) log(`[api] ${line}`);
  };
  child.stdout.on("data", forward);
  child.stderr.on("data", forward);
  child.on("error", (err) => {
    log(`[api] failed to start (is uv on PATH?): ${err.message}`);
  });
  child.on("exit", (code, signal) => {
    log(`[api] exited code=${String(code)} signal=${String(signal)}`);
  });
  return child;
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

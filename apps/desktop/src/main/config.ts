import { randomBytes } from "node:crypto";
import { resolve } from "node:path";

import { DEFAULT_API_PORT } from "../shared/csp";
import type { BackendMode } from "../shared/ipc";

export const LAUNCH_TOKEN_ENV = "TITAN_LAUNCH_TOKEN";
export const DEFAULT_KILL_HOTKEY = "Ctrl+Shift+F12";

export interface MainConfig {
  apiBase: string;
  apiPort: number;
  token: string;
  backend: BackendMode;
  killHotkey: string;
  /** Monorepo root, used to run the API with `uv` in development. */
  repoRoot: string;
}

export interface ResolveOptions {
  isPackaged: boolean;
  /** `app.getAppPath()`: apps/desktop in development. */
  appPath: string;
  randomToken?: () => string;
}

export function newLaunchToken(): string {
  return randomBytes(32).toString("base64url");
}

function port(value: string | undefined, fallback: number): number {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 && parsed < 65536 ? parsed : fallback;
}

/**
 * Settings come from the same `TITAN__SECTION__KEY` variables the Python side reads (Section 9.5).
 * The API always binds 127.0.0.1 (Section 9.6), so only the port is configurable here.
 *
 * Backend modes:
 * - `external`: `TITAN_LAUNCH_TOKEN` is set, so an API started by hand with that token is used.
 * - `managed`: development; the shell runs `uv run titan-api` with a fresh launch token.
 * - `none`: packaged builds (no bundled Python until M10) or `TITAN_BACKEND=none`.
 */
export function resolveMainConfig(env: NodeJS.ProcessEnv, options: ResolveOptions): MainConfig {
  const apiPort = port(env.TITAN__API__PORT, DEFAULT_API_PORT);
  const externalToken = env[LAUNCH_TOKEN_ENV];
  let backend: BackendMode;
  if (externalToken) backend = "external";
  else if (options.isPackaged || env.TITAN_BACKEND === "none") backend = "none";
  else backend = "managed";
  return {
    apiBase: `http://127.0.0.1:${apiPort}`,
    apiPort,
    token: externalToken || (options.randomToken ?? newLaunchToken)(),
    backend,
    killHotkey: env.TITAN__SAFETY__KILL_HOTKEY || DEFAULT_KILL_HOTKEY,
    repoRoot: resolve(options.appPath, "..", ".."),
  };
}

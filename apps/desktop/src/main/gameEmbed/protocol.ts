/**
 * Pure decisions for locking a running game into the Operations Center preview.
 *
 * Unity (KSP) and the SCS sims present with a DXGI flip-model swap chain. That swap chain
 * is specified only for a top-level HWND — SetParent turns the window into a child and the
 * game goes black, and Unity's input stops lining up with the window. Those titles are
 * docked instead: a borderless owned window positioned exactly on the preview rectangle.
 * Owned windows stay above Titan, minimize with it, and still render and take input.
 * SetParent remains the path for a future title that is actually happy as a child.
 */
import type { GameViewRect, GameViewStatus } from "../../shared/ipc";

export interface FoundWindow {
  hwnd: string;
  pid: number;
  title: string;
  className: string;
  exe: string;
  width: number;
  height: number;
}

export interface ProbeResult {
  alive: boolean;
  parent: string;
  owner: string;
  visible: boolean;
  width: number;
  height: number;
}

export type EmbedMode = "embed" | "dock";

export type EmbedPreference = "auto" | EmbedMode;

export interface GameCatalogEntry {
  slug: string;
  exes: readonly string[];
  /** Flip-model / engine windows that break under SetParent. */
  dock: boolean;
}

export const GAME_WINDOWS: readonly GameCatalogEntry[] = [
  { slug: "ksp", exes: ["ksp_x64.exe", "ksp.exe"], dock: true },
  { slug: "ets2", exes: ["eurotrucks2.exe"], dock: true },
  { slug: "ats", exes: ["amtrucks.exe"], dock: true },
];

const SLUGS = new Set(GAME_WINDOWS.map((game) => game.slug));

export function exeBase(exe: string): string {
  const parts = exe.split(/[/\\]/);
  return (parts[parts.length - 1] ?? "").toLowerCase();
}

export function allGameExes(): string[] {
  const names: string[] = [];
  for (const game of GAME_WINDOWS) names.push(...game.exes);
  return names;
}

export function exesForSlug(slug: string | null): string[] {
  if (!slug) return allGameExes();
  const hit = GAME_WINDOWS.find((game) => game.slug === slug);
  return hit ? [...hit.exes] : allGameExes();
}

export function prefersDock(win: Pick<FoundWindow, "exe" | "className">): boolean {
  if (win.className === "UnityWndClass") return true;
  const name = exeBase(win.exe);
  return GAME_WINDOWS.some((game) => game.dock && game.exes.some((exe) => exe === name));
}

export function initialMode(win: FoundWindow, preference: EmbedPreference): EmbedMode {
  if (preference === "embed" || preference === "dock") return preference;
  return prefersDock(win) ? "dock" : "embed";
}

/** Larger visible game windows beat launchers. Unity's class wins ties. */
export function windowScore(win: FoundWindow): number {
  const area = Math.max(0, win.width) * Math.max(0, win.height);
  const unity = win.className === "UnityWndClass" ? 1_000_000_000 : 0;
  const titled = win.title.trim().length > 0 ? 1_000_000 : 0;
  return unity + titled + area;
}

export function pickWindow(windows: readonly FoundWindow[], pid: number | null): FoundWindow | null {
  const matchingPid = pid === null ? [] : windows.filter((win) => win.pid === pid);
  const pool = matchingPid.length > 0 ? matchingPid : windows;
  let best: FoundWindow | null = null;
  let bestScore = -1;
  for (const win of pool) {
    const score = windowScore(win);
    if (score > bestScore) {
      best = win;
      bestScore = score;
    }
  }
  return best;
}

export function viewportToScreenDip(
  contentOrigin: { x: number; y: number },
  viewport: GameViewRect,
): GameViewRect {
  return {
    x: contentOrigin.x + viewport.x,
    y: contentOrigin.y + viewport.y,
    width: Math.max(0, Math.round(viewport.width)),
    height: Math.max(0, Math.round(viewport.height)),
  };
}

/** DIP viewport → physical pixels for a child of the page (the page origin is the client origin). */
export function scaleRect(rect: GameViewRect, scale: number): GameViewRect {
  const factor = scale > 0 && Number.isFinite(scale) ? scale : 1;
  return {
    x: Math.round(rect.x * factor),
    y: Math.round(rect.y * factor),
    width: Math.max(0, Math.round(rect.width * factor)),
    height: Math.max(0, Math.round(rect.height * factor)),
  };
}

/** Electron's native handle is a little-endian HWND. */
export function hwndFromNativeHandle(handle: Buffer): string {
  if (handle.length >= 8) return handle.readBigUInt64LE(0).toString(10);
  if (handle.length >= 4) return handle.readUInt32LE(0).toString(10);
  return "0";
}

export function parseGameViewRect(value: unknown): GameViewRect | null {
  if (typeof value !== "object" || value === null) return null;
  const record = value as Record<string, unknown>;
  const x = record.x;
  const y = record.y;
  const width = record.width;
  const height = record.height;
  if (
    typeof x !== "number" ||
    typeof y !== "number" ||
    typeof width !== "number" ||
    typeof height !== "number"
  ) {
    return null;
  }
  if (![x, y, width, height].every((part) => Number.isFinite(part))) return null;
  return { x, y, width, height };
}

export function parseGameViewTarget(value: unknown): { gameSlug: string | null; pid: number | null } | null {
  if (typeof value !== "object" || value === null) return null;
  const record = value as Record<string, unknown>;
  let gameSlug: string | null = null;
  if (typeof record.gameSlug === "string") {
    const slug = record.gameSlug.trim().toLowerCase();
    if (SLUGS.has(slug)) gameSlug = slug;
  }
  let pid: number | null = null;
  if (typeof record.pid === "number" && Number.isInteger(record.pid) && record.pid > 0) pid = record.pid;
  return { gameSlug, pid };
}

export function parseGameViewHold(value: unknown): { reason: "modal" | "nodock"; on: boolean } | null {
  if (typeof value !== "object" || value === null) return null;
  const record = value as Record<string, unknown>;
  if ((record.reason !== "modal" && record.reason !== "nodock") || typeof record.on !== "boolean")
    return null;
  return { reason: record.reason, on: record.on };
}

/**
 * A docked game is an owned window on top of the page. A rectangle that starts in the
 * session bar, or that runs through the status strip, would cover every Titan control
 * and leave only the native menu. Reject that rectangle. Do not place the game.
 * A tall program that still leaves the status strip is the monitor, not the whole window.
 */
export const SESSION_CHROME_MIN_Y = 48;
export const PROGRAM_MAX_HEIGHT_FRACTION = 0.85;
export const STATUS_STRIP_MIN_PX = 36;
export const COVERING_CHROME_REASON = "Game view is the whole window, so it was not placed.";

export function rectCoversSessionChrome(rect: GameViewRect, contentHeight: number): boolean {
  if (rect.y < SESSION_CHROME_MIN_Y) return true;
  if (!(contentHeight > 0)) return false;
  if (rect.height <= contentHeight * PROGRAM_MAX_HEIGHT_FRACTION) return false;
  const bottomGap = contentHeight - (rect.y + rect.height);
  return bottomGap < STATUS_STRIP_MIN_PX;
}

export function blankStatus(reason: string | null): GameViewStatus {
  return { attached: false, mode: null, title: null, exe: null, pid: null, reason };
}

export function waitingReason(slug: string | null): string {
  if (slug === "ksp") return "Looking for Kerbal Space Program";
  if (slug === "ets2") return "Looking for Euro Truck Simulator 2";
  if (slug === "ats") return "Looking for American Truck Simulator";
  return "Looking for Kerbal Space Program, ETS2, or ATS";
}

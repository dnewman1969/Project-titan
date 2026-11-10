/**
 * Windows can keep the hidden window's first client frame. That frame used to be only
 * `#0b0e14`, so the menu sat on a black page. The size nudge has to happen after the
 * renderer has committed, and it has to wait between the two sizes so Windows cannot
 * coalesce them. A nudge on `ready-to-show` resizes the blank frame and is not the fix.
 */
export const WINDOWS_FIRST_PAINT_FEATURES = ["CalculateNativeWinOcclusion", "WidgetLayering"] as const;

export interface CommandSwitch {
  switchName: string;
  value: string;
}

export function firstPaintSwitches(platform: NodeJS.Platform): CommandSwitch[] {
  if (platform !== "win32") return [];
  return [{ switchName: "disable-features", value: WINDOWS_FIRST_PAINT_FEATURES.join(",") }];
}

export interface CommandLine {
  appendSwitch(switchName: string, value?: string): void;
}

/** Call before `app.whenReady`. Later switches do not affect the first window. */
export function applyFirstPaintSwitches(commandLine: CommandLine, platform: NodeJS.Platform): void {
  for (const item of firstPaintSwitches(platform)) {
    commandLine.appendSwitch(item.switchName, item.value);
  }
}

/** Which of the requested features Chromium actually stored. A unit test of the string is not a painted window. */
export function acceptedFirstPaintFeatures(switchValue: string | undefined): {
  accepted: string[];
  missing: string[];
} {
  const present = new Set(
    (switchValue ?? "")
      .split(",")
      .map((part) => part.trim())
      .filter((part) => part.length > 0),
  );
  const accepted: string[] = [];
  const missing: string[] = [];
  for (const name of WINDOWS_FIRST_PAINT_FEATURES) {
    if (present.has(name)) accepted.push(name);
    else missing.push(name);
  }
  return { accepted, missing };
}

export function describeAcceptedFeatures(switchValue: string | undefined): string {
  const { accepted, missing } = acceptedFirstPaintFeatures(switchValue);
  return `disable-features accepted=${accepted.join(",") || "none"} missing=${missing.join(",") || "none"}`;
}

export interface RevealableWindow {
  show(): void;
}

/**
 * Show the window and stop. `ready-to-show` is the first paint. Resizing it does not
 * paint the Operations Center, and a maximized window ignores `setSize`.
 */
export function revealWindow(win: RevealableWindow, _platform: NodeJS.Platform): void {
  win.show();
}

export interface NudgeWindow {
  isMaximized(): boolean;
  getSize(): readonly number[];
  setSize(width: number, height: number): void;
  /** Used when the window is maximized and `setSize` cannot move it. */
  invalidateClient(): void;
}

/** At 150% or 175% a 1px DIP bump may not move a physical pixel. */
export function layoutBump(scaleFactor: number): number {
  const scale = Number.isFinite(scaleFactor) && scaleFactor > 0 ? scaleFactor : 1;
  return Math.max(2, Math.ceil(scale));
}

/**
 * Relayout after the renderer has committed. The two `setSize` calls are split by
 * `waitForResize` so Windows cannot coalesce them back into a no-op.
 */
export async function nudgeCommittedLayout(
  win: NudgeWindow,
  platform: NodeJS.Platform,
  scaleFactor: number,
  waitForResize: () => Promise<void>,
): Promise<"skipped" | "invalidated" | "resized"> {
  if (platform !== "win32") return "skipped";
  if (win.isMaximized()) {
    win.invalidateClient();
    return "invalidated";
  }
  const [width, height] = win.getSize();
  if (typeof width !== "number" || typeof height !== "number" || width < 2 || height < 2) return "skipped";
  const bump = layoutBump(scaleFactor);
  win.setSize(width, height + bump);
  await waitForResize();
  win.setSize(width, height);
  return "resized";
}

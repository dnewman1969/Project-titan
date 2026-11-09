/**
 * Windows shows the native menu, then keeps the hidden window's first client frame.
 * That frame is only the window background (`#0b0e14`), so the Operations Center never appears.
 * Chromium's occlusion tracker and widget layering are what drop the real paint.
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

export interface RevealableWindow {
  show(): void;
  getSize(): readonly number[];
  setSize(width: number, height: number): void;
}

/**
 * Show the window, then on Windows bump the size and put it back.
 * A same-size show does not invalidate the blank frame the occlusion tracker kept.
 */
export function revealWindow(win: RevealableWindow, platform: NodeJS.Platform): void {
  win.show();
  if (platform !== "win32") return;
  const [width, height] = win.getSize();
  if (typeof width !== "number" || typeof height !== "number" || width < 2 || height < 2) return;
  win.setSize(width, height + 1);
  win.setSize(width, height);
}

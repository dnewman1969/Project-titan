// @vitest-environment node
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const repoRoot = resolve(__dirname, "../../../..");
const indexHtml = readFileSync(resolve(__dirname, "../../src/renderer/index.html"), "utf8");
const startTitan = readFileSync(resolve(repoRoot, "Start-Titan.ps1"), "utf8");
const operations = readFileSync(
  resolve(__dirname, "../../src/renderer/features/operations/OperationsCenter.tsx"),
  "utf8",
);
const theme = readFileSync(resolve(repoRoot, "packages/ts/ui-kit/src/theme.ts"), "utf8");
const reveal = readFileSync(resolve(__dirname, "../../src/main/firstPaint.ts"), "utf8");

/**
 * David launches Start-Titan, which runs `pnpm dev`. The window he sees is the Vite page,
 * not the packaged `app://` file read. A solid black client is that page's first frame with
 * no text. These assertions fail if the shell goes back to an empty root on `#0b0e14`.
 */
describe("black client", () => {
  it("paints a named program frame before React, with a pixel min-height", () => {
    expect(indexHtml).toContain("Opening the Operations Center");
    expect(indexHtml).toContain("PROGRAM");
    expect(indexHtml).toContain("min-height: 760px");
    expect(indexHtml).toContain("border: 1px solid #8ea0b8");
    expect(indexHtml).not.toMatch(/<div id="root"><\/div>/);
    expect(theme).toMatch(/export const SHELL_MIN_HEIGHT_PX = 760/);
    const frame = operations.slice(
      operations.indexOf("export const operationsFrameSize"),
      operations.indexOf("export function railVisible"),
    );
    expect(frame).toContain("minHeight: SHELL_MIN_HEIGHT_PX");
    expect(frame).not.toContain("minHeight: 0");
    expect(theme).toContain("minHeight: SHELL_MIN_HEIGHT_PX");
    const revealFn = reveal.slice(
      reveal.indexOf("export function revealWindow"),
      reveal.indexOf("export interface NudgeWindow"),
    );
    expect(revealFn).toContain("win.show()");
    expect(revealFn).not.toContain("setSize");
  });

  it("does not tell Start-Titan to diagnose a black page from the boot splash", () => {
    expect(startTitan).not.toMatch(/check the boot splash/i);
    expect(startTitan).toContain("Opening the Operations Center");
    expect(startTitan).toContain("[paint]");
    expect(startTitan).toContain("failure page");
  });
});

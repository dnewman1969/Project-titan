import { describe, expect, it } from "vitest";

import { autoDemoEnabled, viteEnvEnabled } from "../../src/renderer/app/viteEnv";

describe("viteEnv", () => {
  it("treats unset and false as off", () => {
    expect(viteEnvEnabled(undefined)).toBe(false);
    expect(viteEnvEnabled("false")).toBe(false);
    expect(viteEnvEnabled("0")).toBe(false);
    expect(viteEnvEnabled("true")).toBe(true);
    expect(viteEnvEnabled("1")).toBe(true);
  });

  it("auto demo follows build default", () => {
    expect(autoDemoEnabled()).toBe(false);
  });
});

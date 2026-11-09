import { describe, expect, it } from "vitest";

import { panelsFromSettings } from "../../src/renderer/app/settings";

const DEFAULT = {
  agents: true,
  webcam: true,
  telemetry: true,
  events: true,
  games: false,
};

describe("panelsFromSettings", () => {
  it("returns defaults when ui.layout is missing", () => {
    expect(panelsFromSettings({}, DEFAULT)).toEqual(DEFAULT);
  });

  it("merges stored panel booleans", () => {
    expect(
      panelsFromSettings(
        { "ui.layout": { panels: { agents: false, webcam: true, telemetry: false } } },
        DEFAULT,
      ),
    ).toEqual({ ...DEFAULT, agents: false, telemetry: false });
  });
});

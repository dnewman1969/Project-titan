import { describe, expect, it } from "vitest";

import { panelsFromSettings } from "../../src/renderer/app/settings";

const DEFAULT = {
  crew: true,
  webcam: true,
  contract: true,
  telemetry: true,
  events: false,
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
    ).toEqual({ ...DEFAULT, crew: false, telemetry: false });
  });
});

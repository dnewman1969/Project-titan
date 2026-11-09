import { describe, expect, it } from "vitest";

import { pickBanterLine } from "../../src/renderer/features/agents/arrogantLines";

describe("agent banter", () => {
  it("prefixes lines with display name", () => {
    const line = pickBanterLine("incredible", {
      persona_slug: "wernher",
      display_name: "Wernher",
      role: "director",
    });
    expect(line).toMatch(/^Wernher:/);
  });
});

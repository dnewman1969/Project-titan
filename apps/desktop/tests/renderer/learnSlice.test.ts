import { describe, expect, it } from "vitest";

import { clearLearnItems, learnItemReceived, learnSlice } from "../../src/renderer/features/learn/learnSlice";

describe("learnSlice", () => {
  it("stores learn-loop items newest first and de-dupes by key", () => {
    let state = learnSlice.getInitialState();
    state = learnSlice.reducer(
      state,
      learnItemReceived({ key: "lessons:play.1", kind: "lesson", text: "Throttle up" }),
    );
    state = learnSlice.reducer(
      state,
      learnItemReceived({
        key: "lessons:feedback.1",
        kind: "outcome",
        text: "Play worked",
        ok: true,
        actionId: "ksp.throttle",
      }),
    );
    state = learnSlice.reducer(
      state,
      learnItemReceived({ key: "lessons:play.1", kind: "lesson", text: "Throttle up" }),
    );
    expect(state.items).toHaveLength(2);
    expect(state.items[0]?.kind).toBe("outcome");
    expect(state.items[0]?.actionId).toBe("ksp.throttle");
    state = learnSlice.reducer(state, clearLearnItems());
    expect(state.items).toHaveLength(0);
  });
});

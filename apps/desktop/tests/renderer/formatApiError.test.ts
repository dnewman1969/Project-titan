import { describe, expect, it } from "vitest";

import { formatApiError } from "../../src/renderer/app/formatApiError";

describe("formatApiError", () => {
  it("surfaces FETCH_ERROR / timeout instead of Unknown API error", () => {
    expect(
      formatApiError({
        status: "FETCH_ERROR",
        error: "AbortError: signal is aborted without reason",
      }),
    ).toMatch(/timed out/i);
    expect(
      formatApiError({
        status: "TIMEOUT_ERROR",
        error: "TimeoutError",
      }),
    ).toMatch(/timed out/i);
    expect(formatApiError({ status: "FETCH_ERROR", error: "ECONNREFUSED" })).toMatch(/Network error/i);
  });

  it("keeps problem+json and parse failures readable", () => {
    expect(
      formatApiError({
        status: 409,
        data: { code: "SESSION_ALREADY_LIVE", title: "Another session is live" },
      }),
    ).toContain("SESSION_ALREADY_LIVE");
    expect(
      formatApiError({
        status: "PARSING_ERROR",
        originalStatus: 200,
        data: "not-json",
        error: "Unexpected token",
      }),
    ).toMatch(/Invalid API response/);
  });
});

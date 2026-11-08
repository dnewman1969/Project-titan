import { ThemeProvider } from "@mui/material/styles";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import {
  AgentAvatar,
  createTitanTheme,
  initials,
  Meter,
  meterFraction,
  ROLE_COLORS,
  roleColor,
  StatusPill,
} from "../src";

function wrap(node: ReactNode) {
  return render(<ThemeProvider theme={createTitanTheme()}>{node}</ThemeProvider>);
}

describe("theme", () => {
  it("is dark and uses no webfonts", () => {
    const theme = createTitanTheme();
    expect(theme.palette.mode).toBe("dark");
    expect(theme.typography.fontFamily).toContain("Segoe UI");
  });

  it("maps dotted roles to their base colour and unknown roles to a fallback", () => {
    expect(roleColor("director")).toBe(ROLE_COLORS.director);
    expect(roleColor("commentator.host")).toBe(ROLE_COLORS.commentator);
    expect(roleColor("mystery")).toMatch(/^#/);
  });
});

describe("StatusPill", () => {
  it("announces label, status and detail", () => {
    wrap(<StatusPill status="down" label="API" detail="connection refused" />);
    const pill = screen.getByRole("status", { name: "API: down (connection refused)" });
    expect(pill).toHaveAttribute("data-status", "down");
    expect(pill).toHaveTextContent("API");
  });
});

describe("Meter", () => {
  it("renders value with unit and aria values", () => {
    wrap(<Meter label="CPU" value={38} max={100} unit="%" />);
    const meter = screen.getByRole("meter", { name: "CPU" });
    expect(meter).toHaveAttribute("aria-valuenow", "38");
    expect(meter).toHaveAttribute("aria-valuetext", "38%");
  });

  it("shows n/a when there is no reading", () => {
    wrap(<Meter label="FPS" value={null} max={144} />);
    expect(screen.getByRole("meter", { name: "FPS" })).toHaveAttribute("aria-valuetext", "n/a");
  });

  it("clamps the fraction", () => {
    expect(meterFraction(-80, -60, 0)).toBe(0);
    expect(meterFraction(-30, -60, 0)).toBe(0.5);
    expect(meterFraction(10, -60, 0)).toBe(1);
    expect(meterFraction(1, 5, 5)).toBe(0);
  });
});

describe("AgentAvatar", () => {
  it("derives initials from persona names", () => {
    expect(initials('Flight Director "Wernher"')).toBe("FW");
    expect(initials("Gene")).toBe("G");
    expect(initials("Jeb Radio")).toBe("JR");
  });

  it("labels role and speaking state", () => {
    wrap(<AgentAvatar name="Gene" role="flight_engineer" speaking />);
    expect(screen.getByLabelText("Gene, flight engineer, speaking")).toHaveTextContent("G");
  });
});

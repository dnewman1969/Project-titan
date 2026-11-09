import { ThemeProvider } from "@mui/material/styles";
import { createTitanTheme } from "@titan/ui-kit";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import {
  FirstRunWizard,
  isFirstRunPending,
  markFirstRunComplete,
} from "../../src/renderer/features/first-run/FirstRunWizard";

describe("FirstRunWizard", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("shows until the user finishes", async () => {
    const user = userEvent.setup();
    render(
      <ThemeProvider theme={createTitanTheme()}>
        <FirstRunWizard />
      </ThemeProvider>,
    );
    expect(screen.getByText("First-run setup")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByRole("heading", { name: "OBS Studio" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Next" }));
    await user.click(screen.getByRole("button", { name: "Finish" }));
    expect(isFirstRunPending()).toBe(false);
  });

  it("tracks completion in localStorage", () => {
    expect(isFirstRunPending()).toBe(true);
    markFirstRunComplete();
    expect(isFirstRunPending()).toBe(false);
  });
});

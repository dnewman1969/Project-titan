import { ThemeProvider } from "@mui/material/styles";
import { createTitanTheme } from "@titan/ui-kit";
import { render, screen } from "@testing-library/react";
import { Provider } from "react-redux";
import { describe, expect, it, vi } from "vitest";

import { makeStore } from "../../src/renderer/app/store";
import { ContractBoard } from "../../src/renderer/features/learn/ContractBoard";
import { contractBoardFromEntries, type BoardEntry } from "../../src/renderer/features/learn/contractBoard";
import { LearnFeedbackStrip } from "../../src/renderer/features/learn/LearnFeedbackStrip";
import { setActiveSession } from "../../src/renderer/features/sessions/sessionsSlice";

const BOARD =
  'Career (funds 12000, science 8, reputation 5). Offered: Reach an altitude of 5,000m [AltitudeRecord] — Reach an altitude of 5,000m (open), advance 1000 funds, completion 5000 funds, 2 science, 1 reputation | Test the LV-T30 "Reliant" Liquid Fuel Engine while landed at Kerbin [PartTest] — Test the LV-T30 "Reliant" Liquid Fuel Engine while landed at Kerbin (open), advance 1000 funds, completion 5000 funds, 2 science, 1 reputation. Active: Reach an altitude of 5,000m [AltitudeRecord] — Reach an altitude of 5,000m (done), advance 1000 funds, completion 5000 funds, 2 science, 1 reputation.';

const CAREER_ENTRIES: BoardEntry[] = [
  {
    section: "discoveries",
    key: "career.board",
    value: { text: BOARD, action_id: null },
  },
  {
    section: "lessons",
    key: "career.accept.reach-11000",
    value: {
      text: "Accepted 'Reach an altitude of 5,000m' because the vessel can climb that high, and the steps are climb to 5,000 m.",
      ok: true,
      contract_key: "altituderecord|reach an altitude of 5000m",
      contract_title: "Reach an altitude of 5,000m",
      contract_type: "AltitudeRecord",
      action_id: "ksp.contract.accept",
    },
  },
  {
    section: "goals",
    key: "career.current",
    value: {
      text: "Reach an altitude of 5,000m: climb to 5,000 m",
      contract_key: "altituderecord|reach an altitude of 5000m",
    },
  },
  {
    section: "lessons",
    key: "career.fail.parachute",
    value: {
      text: "Do not accept contract key `parttest|test the mk16` (Test the Mk16 Parachute) again: out of fuel at 800 m with the parachute test still open.",
      ok: false,
      contract_key: "parttest|test the mk16",
      contract_title: "Test the Mk16 Parachute",
      contract_type: "PartTest",
      action_id: "ksp.contract.accept",
    },
  },
  {
    section: "lessons",
    key: "feedback.1",
    value: {
      text: "Play attempt failed for ksp.fly: unknown error",
      ok: false,
      action_id: "ksp.fly",
    },
  },
];

const STRUCTURED_ENTRIES: BoardEntry[] = [
  {
    section: "discoveries",
    key: "career.snapshot",
    value: {
      funds: 25000,
      science: 12,
      reputation: 4,
      offered: [
        {
          type: "PartTest",
          title: "Test the parachute",
          state: "offered",
          funds_completion: 8000,
          science_completion: 1,
          parameters: [
            {
              title: "Test the Mk16 Parachute while flying",
              completed: false,
              failed: false,
              optional: false,
            },
          ],
        },
      ],
      active: [
        {
          type: "AltitudeRecord",
          title: "Reach 11,000 m",
          state: "active",
          funds_completion: 22000,
          parameters: [
            { title: "Reach an altitude of 11,000 m", completed: true, failed: false, optional: false },
          ],
        },
      ],
    },
  },
];

function renderBoard(entries: BoardEntry[], emptyMessage = "No contracts yet.") {
  const model = contractBoardFromEntries(entries);
  render(
    <ThemeProvider theme={createTitanTheme()}>
      <ContractBoard model={model} emptyMessage={emptyMessage} />
    </ThemeProvider>,
  );
  return model;
}

describe("contract board", () => {
  it("reads offered contracts, the accepted one, its goal and parameters, and a miss", () => {
    const model = renderBoard(CAREER_ENTRIES);
    expect(model.economy).toBe("Career · Funds 12000 · Science 8 · Reputation 5");
    expect(model.offered.map((row) => row.title)).toEqual([
      "Reach an altitude of 5,000m",
      'Test the LV-T30 "Reliant" Liquid Fuel Engine while landed at Kerbin',
    ]);
    expect(model.offered[1]?.parameters.map((row) => row.label)).toEqual([
      'Test the LV-T30 "Reliant" Liquid Fuel Engine while landed at Kerbin',
    ]);
    expect(model.offered[1]?.reward).toBe(
      "advance 1000 funds, completion 5000 funds, 2 science, 1 reputation",
    );
    expect(model.accepted?.title).toBe("Reach an altitude of 5,000m");
    expect(model.accepted?.goals).toEqual(["Reach an altitude of 5,000m: climb to 5,000 m"]);
    expect(model.accepted?.parameters).toEqual([
      { label: "Reach an altitude of 5,000m", state: "done", optional: false },
    ]);
    expect(model.misses[0]?.lesson).toBe(
      "Test the Mk16 Parachute will not be accepted again. Out of fuel at 800 m with the parachute test still open.",
    );

    const board = screen.getByLabelText("Contract board");
    expect(board).toHaveTextContent("Offered");
    expect(board).toHaveTextContent("Accepted");
    expect(board).toHaveTextContent("Goals");
    expect(board).toHaveTextContent("Parameters");
    expect(board).toHaveTextContent("Lessons from misses");
    expect(board).toHaveTextContent("Altitude record");
    expect(board).toHaveTextContent("Part test");
    expect(board).toHaveTextContent("climb to 5,000 m");
    expect(board).toHaveTextContent("Reliant");
    expect(board).toHaveTextContent(
      "Reward: advance 1000 funds, completion 5000 funds, 2 science, 1 reputation",
    );
    expect(board).toHaveTextContent("will not be accepted again");
    expect(board).not.toHaveTextContent("Waiting for discoveries");
    expect(board.textContent).not.toMatch(/ksp\.|career\.|contract key|`|stub/i);
    expect(board).not.toHaveTextContent("Play attempt failed");
  });

  it("reads a structured contract snapshot", () => {
    renderBoard(STRUCTURED_ENTRIES);
    const board = screen.getByLabelText("Contract board");
    expect(board).toHaveTextContent("Funds 25000 · Science 12 · Reputation 4");
    expect(board).toHaveTextContent("Test the parachute");
    expect(board).toHaveTextContent("Test the Mk16 Parachute while flying");
    expect(board).toHaveTextContent("Open");
    expect(board).toHaveTextContent("This contract is active.");
    expect(board).toHaveTextContent("Done");
    expect(board).toHaveTextContent("Reward: completion 8000 funds, 1 science");
    expect(board).toHaveTextContent("Reward: completion 22000 funds");
    expect(board.textContent).not.toMatch(/ksp\.|career\.|stub/i);
  });

  it("says when the save is not a career game", () => {
    renderBoard([
      {
        section: "discoveries",
        key: "career.mode",
        value: {
          text: "This save is sandbox, not a career or science game. Contracts are not available, so none will be accepted or invented.",
          action_id: null,
        },
      },
    ]);
    const board = screen.getByLabelText("Contract board");
    expect(board).toHaveTextContent("This save is sandbox, not a career or science game.");
    expect(board).toHaveTextContent("No contracts offered.");
    expect(board).toHaveTextContent("No contract has been accepted.");
    expect(board).toHaveTextContent("No lessons from misses.");
    expect(board).not.toHaveTextContent("No contracts yet.");
  });

  it("stays empty until the blackboard reports contracts", () => {
    renderBoard([]);
    expect(screen.getByLabelText("Contract board")).toHaveTextContent("No contracts yet.");
    expect(screen.queryByRole("heading", { name: "Offered" })).toBeNull();
  });
});

describe("Operations Center contract strip", () => {
  it("replaces the waiting line with the empty contract board", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ bb_version: 1, entries: [] }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        ),
      ),
    );
    const store = makeStore();
    store.dispatch(
      setActiveSession({
        id: "6b1e0b1e-0000-4000-8000-000000000051",
        title: "Career",
        playEnabled: true,
        gameSlug: "ksp",
      }),
    );
    render(
      <Provider store={store}>
        <ThemeProvider theme={createTitanTheme()}>
          <LearnFeedbackStrip />
        </ThemeProvider>
      </Provider>,
    );
    expect(await screen.findByText(/No contracts yet/)).toBeInTheDocument();
    expect(screen.getByLabelText("Contracts")).not.toHaveTextContent("Waiting for discoveries");
    expect(screen.getByText("Play on")).toBeInTheDocument();
  });

  it("shows fixture contracts from the session blackboard", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ bb_version: 4, entries: CAREER_ENTRIES }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        ),
      ),
    );
    const store = makeStore();
    store.dispatch(
      setActiveSession({
        id: "6b1e0b1e-0000-4000-8000-000000000051",
        title: "Career",
        playEnabled: true,
        gameSlug: "ksp",
      }),
    );
    render(
      <Provider store={store}>
        <ThemeProvider theme={createTitanTheme()}>
          <LearnFeedbackStrip />
        </ThemeProvider>
      </Provider>,
    );
    expect(await screen.findByRole("heading", { name: "Accepted" })).toBeInTheDocument();
    const region = screen.getByLabelText("Contracts");
    expect(region).toHaveTextContent("Reach an altitude of 5,000m");
    expect(region).toHaveTextContent("Lessons from misses");
    expect(region).toHaveTextContent("will not be accepted again");
    expect(region.textContent).not.toMatch(/ksp\.|career\.|contract key|`/);
  });
});

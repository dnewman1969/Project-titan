import { ThemeProvider } from "@mui/material/styles";
import { SystemMetricsSchema } from "@titan/protocol";
import { createTitanTheme } from "@titan/ui-kit";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Provider } from "react-redux";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import type { KillSwitchEvent, TitanBridge } from "../../src/shared/ipc";
import { App } from "../../src/renderer/app/App";
import { makeStore } from "../../src/renderer/app/store";
import { gridTemplate } from "../../src/renderer/features/operations/OperationsCenter";
import { formatMetrics } from "../../src/renderer/features/telemetry/TelemetryBar";
import { metricsReceived } from "../../src/renderer/features/telemetry/systemSlice";

const STATUS_BODY = {
  services: [{ name: "api", state: "up", pid: 1, restarts: 0, since: "2026-11-08T12:00:00Z" }],
  dependencies: { postgres: { state: "up", version: "16.15", detail: null } },
  resource_guard_level: "L0",
};

const METRICS = SystemMetricsSchema.parse({
  ts: "2026-11-08T12:00:00Z",
  game_fps: 71.6,
  game_frametime_p99_ms: 18.2,
  cpu_pct: 38.4,
  ram_used_mb: 21504,
  ram_total_mb: 32768,
  gpu: [
    {
      index: 0,
      name: "RTX",
      util_pct: 81,
      vram_used_mb: 10035,
      vram_total_mb: 12288,
      temp_c: 70,
      encoder_util_pct: 12,
    },
  ],
  tokens_per_min: 4100,
  llm_queue_depth: 0,
  goals_active: 2,
  tasks_open: 5,
  resource_guard_level: "L0",
});

interface FakeBridge {
  bridge: TitanBridge;
  kill: (event: KillSwitchEvent) => void;
  menu: (id: string) => void;
}

function fakeBridge(): FakeBridge {
  const kills = new Set<(e: KillSwitchEvent) => void>();
  const menus = new Set<(id: string) => void>();
  return {
    bridge: {
      apiBase: "http://127.0.0.1:8765",
      token: "test-token",
      platform: "win32",
      backend: "managed",
      killHotkey: "Ctrl+Shift+F12",
      versions: { app: "0.1.0", electron: "45.2.3", chrome: "140", node: "22" },
      onKillSwitch: (l) => {
        kills.add(l);
        return () => kills.delete(l);
      },
      onMenuCommand: (l) => {
        menus.add(l);
        return () => menus.delete(l);
      },
    },
    kill: (e) => {
      kills.forEach((l) => {
        l(e);
      });
    },
    menu: (id) => {
      menus.forEach((l) => {
        l(id);
      });
    },
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

function renderApp(store = makeStore()) {
  render(
    <Provider store={store}>
      <ThemeProvider theme={createTitanTheme()}>
        <App />
      </ThemeProvider>
    </Provider>,
  );
  return store;
}

let shell: FakeBridge;
let fetchMock: Mock<(input: Request) => Promise<Response>>;

beforeEach(() => {
  shell = fakeBridge();
  window.titan = shell.bridge;
  fetchMock = vi.fn((input: Request) => {
    const url = input.url;
    if (url.endsWith("/api/v1/health")) return Promise.resolve(jsonResponse({ status: "ok" }));
    if (url.endsWith("/api/v1/system/status")) return Promise.resolve(jsonResponse(STATUS_BODY));
    return Promise.resolve(jsonResponse({ title: "Not Found" }, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  delete window.titan;
});

describe("Operations Center", () => {
  it("renders every main-screen region from Section 2.13", () => {
    renderApp();
    for (const name of [
      "Titan status bar",
      "Game window",
      "AI Agents",
      "Webcam",
      "Telemetry bar",
      "Event Log",
    ]) {
      expect(
        screen.getByRole(name === "Titan status bar" ? "banner" : "region", { name }),
      ).toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: /kill/i })).toBeInTheDocument();
    expect(screen.getAllByRole("listitem").length).toBeGreaterThanOrEqual(5);
    expect(screen.getByRole("textbox", { name: "Message the crew" })).toBeDisabled();
  });

  it("shows API and database health from the backend, sending the launch token", async () => {
    renderApp();
    await waitFor(() => {
      expect(screen.getByRole("status", { name: /^API: ok/ })).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByRole("status", { name: /^Database: ok/ })).toBeInTheDocument();
    });
    const statusCall = fetchMock.mock.calls
      .map(([request]) => request)
      .find((r) => r.url.endsWith("/system/status"));
    expect(statusCall?.headers.get("authorization")).toBe("Bearer test-token");
    expect(
      within(screen.getByRole("region", { name: "Event Log" })).getByText("API connected"),
    ).toBeInTheDocument();
  });

  it("reports the API as down when it is unreachable", async () => {
    fetchMock.mockImplementation(() => Promise.reject(new TypeError("Failed to fetch")));
    renderApp();
    await waitFor(() => {
      expect(screen.getByRole("status", { name: /^API: down/ })).toBeInTheDocument();
    });
    expect(screen.getByText(/API not reachable yet/)).toBeInTheDocument();
  });

  it("engages the kill switch from the global hotkey and from the button", async () => {
    const user = userEvent.setup();
    const store = renderApp();
    act(() => {
      shell.kill({ source: "hotkey", at: "2026-11-08T12:00:00.000Z" });
    });
    expect(screen.getByRole("alert")).toHaveTextContent("Kill switch engaged");
    expect(store.getState().safety).toMatchObject({ killed: true, last_kill_source: "hotkey" });
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /kill/i }));
    expect(store.getState().safety.last_kill_source).toBe("button");
    expect(store.getState().events.entries.filter((e) => e.category === "safety")).toHaveLength(2);
  });

  it("handles menu commands: panel toggles, About, and milestone notices", async () => {
    renderApp();
    act(() => {
      shell.menu("view.toggle.webcam");
    });
    expect(screen.queryByRole("region", { name: "Webcam" })).not.toBeInTheDocument();
    act(() => {
      shell.menu("view.toggle.webcam");
    });
    expect(screen.getByRole("region", { name: "Webcam" })).toBeInTheDocument();

    act(() => {
      shell.menu("help.about");
    });
    const about = await screen.findByRole("dialog", { name: "About Titan" });
    expect(within(about).getByText("45.2.3")).toBeInTheDocument();

    act(() => {
      shell.menu("view.blackboardInspector");
    });
    expect(await screen.findByText("Blackboard Inspector arrives in M7.T5.")).toBeInTheDocument();
  });

  it("filters the event log by category", async () => {
    const user = userEvent.setup();
    renderApp();
    await user.click(screen.getByRole("button", { name: /kill/i }));
    const log = screen.getByRole("region", { name: "Event Log" });
    await user.click(within(log).getByRole("button", { name: "System" }));
    expect(within(log).queryByText(/Kill switch engaged/)).not.toBeInTheDocument();
    await user.click(within(log).getByRole("button", { name: "Safety" }));
    expect(within(log).getByText(/Kill switch engaged/)).toBeInTheDocument();
  });

  it("renders live system metrics in the telemetry bar", () => {
    const store = renderApp();
    act(() => {
      store.dispatch(metricsReceived(METRICS));
      store.dispatch(metricsReceived({ ...METRICS, cpu_pct: 41 }));
    });
    expect(screen.getByTestId("metric-cpu")).toHaveTextContent("41%");
    expect(screen.getByTestId("metric-fps")).toHaveTextContent("72");
    expect(screen.getByRole("img", { name: "CPU history" })).toBeInTheDocument();
  });
});

describe("formatMetrics", () => {
  it("shows n/a for everything without metrics", () => {
    expect(formatMetrics(null).every((c) => c.value === "n/a")).toBe(true);
  });

  it("formats a full SystemMetrics frame", () => {
    const values = Object.fromEntries(formatMetrics(METRICS).map((c) => [c.key, c.value]));
    expect(values).toEqual({
      fps: "72",
      cpu: "38%",
      gpu: "81%",
      vram: "9.8/12.0G",
      ram: "21.0G",
      tokens: "4.1k/m",
      goals: "2",
      tasks: "5",
    });
  });

  it("shows n/a for GPU fields on non-NVIDIA systems and without a game", () => {
    const values = Object.fromEntries(
      formatMetrics({ ...METRICS, gpu: [], game_fps: null }).map((c) => [c.key, c.value]),
    );
    expect(values).toMatchObject({ fps: "n/a", gpu: "n/a", vram: "n/a", cpu: "38%" });
  });
});

describe("gridTemplate", () => {
  it("lays out all panels", () => {
    const t = gridTemplate({ agents: true, webcam: true, telemetry: true, events: true });
    expect(t.areas).toBe('"top top" "game game" "agents webcam" "telemetry telemetry" "events events"');
  });

  it("collapses hidden panels", () => {
    const t = gridTemplate({ agents: false, webcam: true, telemetry: false, events: false });
    expect(t.areas).toBe('"top top" "game game" "webcam webcam"');
    expect(t.rows.split(" ").length).toBeGreaterThanOrEqual(3);
  });
});

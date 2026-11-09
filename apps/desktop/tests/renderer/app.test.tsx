import { ThemeProvider } from "@mui/material/styles";
import { SystemMetricsSchema } from "@titan/protocol";
import { createTitanTheme } from "@titan/ui-kit";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Provider } from "react-redux";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import type { KillSwitchEvent, SupervisorUpdate, TitanBridge } from "../../src/shared/ipc";
import { App } from "../../src/renderer/app/App";
import { markFirstRunComplete } from "../../src/renderer/features/first-run/FirstRunWizard";
import { makeStore } from "../../src/renderer/app/store";
import { gridTemplate } from "../../src/renderer/features/operations/OperationsCenter";
import { formatMetrics } from "../../src/renderer/features/telemetry/TelemetryBar";
import { metricsReceived } from "../../src/renderer/features/telemetry/systemSlice";
import { summarizeServices } from "../../src/renderer/app/useApiStatus";
import { LiveConnection, wsUrl } from "../../src/renderer/app/ws";

const SINCE = "2026-11-08T12:00:00Z";

const STATUS_BODY = {
  services: [
    { name: "postgres", state: "up", pid: 10, restarts: 0, since: SINCE, detail: "16.15", kind: "managed" },
    { name: "redis", state: "up", pid: null, restarts: 0, since: SINCE, detail: "7.4", kind: "external" },
    { name: "api", state: "up", pid: 1, restarts: 0, since: SINCE, detail: null, kind: "managed" },
  ],
  dependencies: { postgres: { state: "up", version: "16.15", detail: null } },
  resource_guard_level: "L0",
};

const SAFETY = {
  killed: false,
  armed: false,
  control_owner: "none",
  last_kill_at: null,
  last_kill_source: null,
  policy_version: 1,
};

function supervisorStatus(
  ready: boolean,
  events: { seq: number; kind: string; process: string; detail?: string }[],
) {
  return {
    started_at: SINCE,
    ready,
    services: [
      {
        name: "postgres",
        state: ready ? "up" : "starting",
        pid: 10,
        restarts: 0,
        since: SINCE,
        detail: null,
        kind: "managed",
      },
      {
        name: "api",
        state: ready ? "up" : "unknown",
        pid: null,
        restarts: 0,
        since: SINCE,
        detail: "waiting to start",
        kind: "managed",
      },
    ],
    events: events.map((e) => ({ ts: SINCE, detail: null, ...e })),
  };
}

/** Records what the client sends; tests play the server side. */
class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  sent: unknown[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: ((event: { code: number }) => void) | null = null;

  constructor(readonly url: string) {
    FakeWebSocket.instances.push(this);
  }

  send(data: string): void {
    this.sent.push(JSON.parse(data));
  }

  close(): void {
    this.onclose?.({ code: 1000 });
  }

  serverSends(frame: unknown): void {
    this.onmessage?.({ data: JSON.stringify(frame) });
  }
}

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
  supervisor: (update: SupervisorUpdate) => void;
}

function fakeBridge(snapshot: SupervisorUpdate | null = null): FakeBridge {
  const kills = new Set<(e: KillSwitchEvent) => void>();
  const menus = new Set<(id: string) => void>();
  const supervisors = new Set<(u: SupervisorUpdate) => void>();
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
      onSupervisorUpdate: (l) => {
        supervisors.add(l);
        return () => supervisors.delete(l);
      },
      getSupervisorStatus: () => Promise.resolve(snapshot),
      openPath: () => Promise.resolve(""),
      pickExecutable: () => Promise.resolve(null),
      openExternal: () => Promise.resolve(),
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
    supervisor: (update) => {
      supervisors.forEach((l) => {
        l(update);
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
  markFirstRunComplete();
  shell = fakeBridge();
  window.titan = shell.bridge;
  FakeWebSocket.instances = [];
  vi.stubGlobal("WebSocket", FakeWebSocket);
  fetchMock = vi.fn((input: Request) => {
    const url = input.url;
    if (url.endsWith("/api/v1/health")) return Promise.resolve(jsonResponse({ status: "ok" }));
    if (url.endsWith("/api/v1/settings") && input.method === "GET")
      return Promise.resolve(jsonResponse({ version: 1, values: {} }));
    if (url.endsWith("/api/v1/settings") && input.method === "PATCH")
      return Promise.resolve(
        jsonResponse({
          version: 2,
          values: {
            "ui.layout": {
              panels: { agents: true, webcam: false, telemetry: true, events: true, games: false },
            },
          },
        }),
      );
    if (url.endsWith("/api/v1/sessions") && input.method === "POST")
      return Promise.resolve(jsonResponse({ title: "Not Found" }, 404));
    if (url.endsWith("/api/v1/system/status")) return Promise.resolve(jsonResponse(STATUS_BODY));
    if (url.endsWith("/api/v1/safety/kill"))
      return Promise.resolve(
        jsonResponse({ ...SAFETY, killed: true, last_kill_source: "button", last_kill_at: SINCE }),
      );
    if (url.endsWith("/api/v1/safety/resume")) return Promise.resolve(jsonResponse(SAFETY));
    return Promise.resolve(jsonResponse({ title: "Not Found" }, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  delete window.titan;
  vi.unstubAllGlobals();
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
    expect(screen.getByRole("textbox", { name: "Message the crew" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Brag" })).toBeInTheDocument();
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
    await user.click(screen.getByRole("button", { name: "Resume" }));
    await waitFor(() => {
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
    const resume = fetchMock.mock.calls.map(([r]) => r).find((r) => r.url.endsWith("/safety/resume"));
    expect(await resume?.clone().json()).toEqual({ confirm: "RESUME" });

    await user.click(screen.getByRole("button", { name: /kill/i }));
    expect(store.getState().safety.last_kill_source).toBe("button");
    expect(store.getState().events.entries.filter((e) => e.category === "safety")).toHaveLength(2);
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([r]) => r.url.endsWith("/safety/kill") && r.method === "POST")).toBe(
        true,
      );
    });
  });

  it("handles menu commands: panel toggles, About, and milestone notices", async () => {
    renderApp();
    await waitFor(() => {
      expect(fetchMock.mock.calls.some(([r]) => r.url.endsWith("/settings"))).toBe(true);
    });
    act(() => {
      shell.menu("view.toggle.webcam");
    });
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([r]) => r.url.endsWith("/settings") && r.method === "PATCH" && r.headers.get("if-match") === "1",
        ),
      ).toBe(true);
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

    act(() => {
      shell.menu("file.newSession");
    });
    const sessionDialog = await screen.findByRole("dialog", { name: "New session" });
    await userEvent
      .setup()
      .click(within(sessionDialog).getByRole("button", { name: "Start learn and play" }));
    expect(await screen.findByText(/Session API is not on this backend yet/)).toBeInTheDocument();
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

describe("platform services (M1)", () => {
  it("shows the boot splash until the supervisor is ready and logs supervisor events", async () => {
    shell = fakeBridge({ process: "starting", detail: null, status: null });
    window.titan = shell.bridge;
    renderApp();
    const splash = await screen.findByRole("dialog", { name: "Starting Titan" });
    expect(within(splash).getByText("Launching titan-supervisor…")).toBeInTheDocument();
    act(() => {
      shell.supervisor({
        process: "running",
        detail: null,
        status: supervisorStatus(false, [
          { seq: 1, kind: "starting", process: "postgres" },
          { seq: 2, kind: "exited", process: "api", detail: "exit code 1" },
        ]),
      });
    });
    expect(within(splash).getByText("Database (PostgreSQL)")).toBeInTheDocument();
    expect(within(splash).getByRole("status", { name: /^postgres: degraded/ })).toBeInTheDocument();
    expect(within(splash).getByText("waiting to start")).toBeInTheDocument();
    const log = screen.getByRole("region", { name: "Event Log" });
    expect(within(log).getByText("api exited (exit code 1)")).toBeInTheDocument();
    act(() => {
      shell.supervisor({
        process: "running",
        detail: null,
        status: supervisorStatus(true, [
          { seq: 2, kind: "exited", process: "api", detail: "exit code 1" },
          { seq: 3, kind: "healthy", process: "api" },
        ]),
      });
    });
    expect(screen.queryByRole("dialog", { name: "Starting Titan" })).not.toBeInTheDocument();
    expect(within(log).getAllByText("api exited (exit code 1)")).toHaveLength(1);
    expect(within(log).getByText("api healthy")).toBeInTheDocument();
  });

  it("can continue past the boot splash", async () => {
    const user = userEvent.setup();
    shell = fakeBridge({
      process: "exited",
      detail: "exited (code 2) repeatedly; restart Titan",
      status: null,
    });
    window.titan = shell.bridge;
    renderApp();
    expect(await screen.findByText("Titan services stopped")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Continue without waiting" }));
    expect(screen.queryByRole("dialog", { name: "Starting Titan" })).not.toBeInTheDocument();
  });

  it("shows no boot splash without a managed backend", () => {
    window.titan = { ...shell.bridge, backend: "external" };
    renderApp();
    expect(screen.queryByRole("dialog", { name: "Starting Titan" })).not.toBeInTheDocument();
  });

  it("summarizes every supervised service in the top bar", async () => {
    renderApp();
    await waitFor(() => {
      expect(screen.getByRole("status", { name: "Services: ok (3 running)" })).toBeInTheDocument();
    });
    expect(summarizeServices(undefined)).toEqual(["unknown", "no status yet"]);
    expect(
      summarizeServices([
        { name: "postgres", state: "up" },
        { name: "chroma", state: "failed" },
        { name: "api", state: "degraded" },
      ]),
    ).toEqual(["down", "chroma failed, api degraded"]);
  });

  it("streams system.metrics and system.safety over the WS gateway", () => {
    const store = renderApp();
    const socket = FakeWebSocket.instances.at(-1);
    if (!socket) throw new Error("no WebSocket opened");
    expect(socket.url).toBe("ws://127.0.0.1:8765/api/v1/ws");
    act(() => {
      socket.onopen?.();
    });
    expect(socket.sent[0]).toEqual({ op: "auth", token: "test-token", client: "desktop/0.1.0" });
    act(() => {
      socket.serverSends({ op: "ack", req_id: "auth", ok: true, error: null });
    });
    expect(socket.sent.slice(1)).toEqual([
      { op: "subscribe", req_id: "s1", channel: "system.metrics" },
      { op: "subscribe", req_id: "s2", channel: "system.safety" },
    ]);
    act(() => {
      socket.serverSends({
        op: "msg",
        channel: "system.metrics",
        seq: "1-0",
        ts: SINCE,
        type: "system.metrics",
        data: { ...METRICS, cpu_pct: 12, game_fps: null },
      });
    });
    expect(screen.getByTestId("metric-cpu")).toHaveTextContent("12%");
    expect(screen.getByTestId("metric-fps")).toHaveTextContent("n/a");
    act(() => {
      socket.serverSends({
        op: "msg",
        channel: "system.safety",
        seq: "2-0",
        ts: SINCE,
        type: "safety.state",
        data: { ...SAFETY, killed: true, last_kill_source: "hotkey", last_kill_at: SINCE },
      });
    });
    expect(screen.getByRole("alert")).toHaveTextContent("Kill switch engaged");
    act(() => {
      socket.serverSends({
        op: "msg",
        channel: "system.metrics",
        seq: "3-0",
        ts: SINCE,
        type: "system.metrics",
        data: { cpu_pct: "bad" },
      });
      socket.serverSends("not a frame");
    });
    expect(store.getState().system.history).toHaveLength(1);
  });
});

describe("LiveConnection", () => {
  it("reconnects with backoff and reports a rejected token", () => {
    vi.useFakeTimers();
    try {
      const onConnection = vi.fn();
      const connection = new LiveConnection({
        url: wsUrl("http://127.0.0.1:8765"),
        token: "t",
        client: "test",
        handlers: { onMetrics: vi.fn(), onSafety: vi.fn(), onConnection },
        WebSocketImpl: FakeWebSocket as unknown as typeof WebSocket,
      });
      connection.start();
      const first = FakeWebSocket.instances.at(-1);
      first?.onclose?.({ code: 4401 });
      expect(onConnection).toHaveBeenCalledWith(false, "launch token rejected");
      const before = FakeWebSocket.instances.length;
      vi.advanceTimersByTime(1000);
      expect(FakeWebSocket.instances.length).toBe(before + 1);
      FakeWebSocket.instances.at(-1)?.onclose?.({ code: 1006 });
      vi.advanceTimersByTime(1000);
      expect(FakeWebSocket.instances.length).toBe(before + 1);
      vi.advanceTimersByTime(1000);
      expect(FakeWebSocket.instances.length).toBe(before + 2);
      connection.stop();
      vi.advanceTimersByTime(20_000);
      expect(FakeWebSocket.instances.length).toBe(before + 2);
    } finally {
      vi.useRealTimers();
    }
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
    const t = gridTemplate({
      agents: true,
      webcam: true,
      telemetry: true,
      events: true,
      games: false,
    });
    expect(t.areas).toBe('"top top" "game game" "agents webcam" "telemetry telemetry" "events events"');
  });

  it("collapses hidden panels", () => {
    const t = gridTemplate({
      agents: false,
      webcam: true,
      telemetry: false,
      events: false,
      games: false,
    });
    expect(t.areas).toBe('"top top" "game game" "webcam webcam"');
    expect(t.rows.split(" ").length).toBeGreaterThanOrEqual(3);
  });
});

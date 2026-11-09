import { ThemeProvider } from "@mui/material/styles";
import { createTitanTheme } from "@titan/ui-kit";
import { render, screen, waitFor } from "@testing-library/react";
import { Provider } from "react-redux";
import { afterEach, describe, expect, it, vi } from "vitest";

import { makeStore } from "../../src/renderer/app/store";
import {
  cameraNameMatches,
  captureTrackViews,
  levelDbFromTimeDomain,
  pickObsbotDevice,
} from "../../src/renderer/features/webcam/devices";
import {
  timelineEventLabel,
  timelineEventText,
} from "../../src/renderer/features/recording/RecTimelineStrip";
import { WebcamPanel } from "../../src/renderer/features/webcam/WebcamPanel";

describe("camera selection", () => {
  it("matches OBSBOT and Tiny labels and ignores other cameras", () => {
    expect(cameraNameMatches("OBSBOT Tiny 4K")).toBe(true);
    expect(cameraNameMatches("USB Tiny Cam")).toBe(true);
    expect(cameraNameMatches("Integrated Camera")).toBe(false);
    expect(
      pickObsbotDevice([
        { kind: "videoinput", label: "Integrated Camera", deviceId: "a" },
        { kind: "videoinput", label: "OBSBOT Tiny", deviceId: "tiny" },
        { kind: "audioinput", label: "OBSBOT Tiny", deviceId: "mic" },
      ]),
    ).toEqual({ deviceId: "tiny", label: "OBSBOT Tiny" });
  });

  it("turns a silent analyser buffer into the floor of the meter", () => {
    expect(levelDbFromTimeDomain(new Uint8Array(16).fill(128))).toBe(-60);
  });

  it("does not label gameplay, mic, or webcam tracks as stub", () => {
    const rows = captureTrackViews({
      obsConnected: false,
      obsRecording: false,
      cameraLabel: null,
      micLive: false,
    });
    const text = rows.map((row) => `${row.label} ${row.pill} ${row.detail}`).join(" ");
    expect(text).not.toMatch(/stub/i);
    expect(rows.find((row) => row.id === "game_audio")?.pill).toBe("OBS not running");
    expect(rows.find((row) => row.id === "mic_audio")?.pill).toBe("no device");
    expect(rows.find((row) => row.id === "webcam_video")?.pill).toBe("no device");
    const live = captureTrackViews({
      obsConnected: true,
      obsRecording: true,
      cameraLabel: "OBSBOT Tiny",
      micLive: true,
    });
    expect(live.find((row) => row.id === "webcam_video")?.detail).toBe("OBSBOT Tiny");
    expect(live.every((row) => row.pill === "rec")).toBe(true);
  });
});

describe("timeline labels", () => {
  it("shows OBS StartRecord and does not say video stub", () => {
    expect(timelineEventLabel("recording.start")).toBe("REC start");
    expect(timelineEventText({ kind: "recording.start", message: "OBS StartRecord" })).toBe(
      "OBS StartRecord",
    );
    expect(timelineEventLabel("video.stub")).toBe("OBS not running");
    expect(timelineEventText({ kind: "video.stub", message: "writing stub tracks" })).toBe("OBS not running");
  });
});

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

describe("WebcamPanel", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows OBS not running and no camera without saying stub", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = requestUrl(input);
        if (url.includes("/capture/obs")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                state: "down",
                detail: "OBS not running",
                host: "127.0.0.1",
                port: 4455,
                connected: false,
                version: null,
                provision: null,
                webcam: { selected: false, detail: "OBS not running" },
              }),
              { status: 200, headers: { "Content-Type": "application/json" } },
            ),
          );
        }
        return Promise.resolve(new Response("not found", { status: 404 }));
      }),
    );
    render(
      <Provider store={makeStore()}>
        <ThemeProvider theme={createTitanTheme()}>
          <WebcamPanel />
        </ThemeProvider>
      </Provider>,
    );
    expect((await screen.findAllByText("OBS not running")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("No camera").length).toBeGreaterThan(0);
    expect(screen.getAllByText("no device").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Webcam").textContent).not.toMatch(/stub/i);
  });

  it("previews an OBSBOT Tiny when the browser exposes that label", async () => {
    const track = {
      kind: "video",
      label: "OBSBOT Tiny",
      stop: vi.fn(),
      getSettings: () => ({ deviceId: "tiny" }),
    };
    const stream = {
      getTracks: () => [track],
      getVideoTracks: () => [track],
      getAudioTracks: () => [],
    };
    const devices = [
      { kind: "videoinput", label: "OBSBOT Tiny", deviceId: "tiny", groupId: "g", toJSON: () => ({}) },
    ];
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        enumerateDevices: vi.fn(() => Promise.resolve(devices)),
        getUserMedia: vi.fn(() => Promise.resolve(stream)),
      },
    });
    class FakeAudioContext {
      createMediaStreamSource(): { connect: () => void } {
        return {
          connect() {
            return undefined;
          },
        };
      }
      createAnalyser(): { fftSize: number; getByteTimeDomainData: (buffer: Uint8Array) => void } {
        return {
          fftSize: 256,
          getByteTimeDomainData(buffer: Uint8Array) {
            buffer.fill(128);
          },
        };
      }
      close(): Promise<void> {
        return Promise.resolve();
      }
    }
    vi.stubGlobal("AudioContext", FakeAudioContext);
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = requestUrl(input);
        if (url.includes("/capture/obs")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                state: "up",
                detail: null,
                host: "127.0.0.1",
                port: 4455,
                connected: true,
                version: { obsVersion: "30.2.0" },
                provision: { status: "planned" },
                record: { active: false, paused: false, duration_ms: 0 },
                webcam: {
                  selected: true,
                  input_name: "Titan Webcam",
                  device_name: "OBSBOT Tiny",
                  detail: "OBS source Titan Webcam → OBSBOT Tiny",
                },
              }),
              { status: 200, headers: { "Content-Type": "application/json" } },
            ),
          );
        }
        return Promise.resolve(new Response("not found", { status: 404 }));
      }),
    );
    render(
      <Provider store={makeStore()}>
        <ThemeProvider theme={createTitanTheme()}>
          <WebcamPanel />
        </ThemeProvider>
      </Provider>,
    );
    expect(await screen.findByText("OBS 30.2.0")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByLabelText("Webcam preview")).toBeInTheDocument();
    });
    expect(screen.getAllByText("OBSBOT Tiny").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Webcam").textContent).not.toMatch(/stub/i);
  });
});

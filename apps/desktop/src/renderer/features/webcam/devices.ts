import type { Status } from "@titan/ui-kit";

/** USB / browser / OBS device names for the OBSBOT Tiny family. */
export function cameraNameMatches(label: string): boolean {
  const folded = label.toLowerCase();
  return folded.includes("obsbot") || folded.includes("tiny");
}

export interface CameraChoice {
  deviceId: string;
  label: string;
}

export function pickObsbotDevice(
  devices: ReadonlyArray<{ kind: string; label: string; deviceId: string }>,
): CameraChoice | null {
  const match = devices.find((device) => device.kind === "videoinput" && cameraNameMatches(device.label));
  if (!match) return null;
  return { deviceId: match.deviceId, label: match.label };
}

/** RMS of an analyser time-domain buffer (0–255) as dBFS, clamped to [-60, 0]. */
export function levelDbFromTimeDomain(samples: ArrayLike<number>): number {
  if (samples.length === 0) return -60;
  let sum = 0;
  for (let index = 0; index < samples.length; index += 1) {
    const sample = samples[index] ?? 128;
    const centered = (sample - 128) / 128;
    sum += centered * centered;
  }
  const rms = Math.sqrt(sum / samples.length);
  if (rms <= 1e-4) return -60;
  const db = 20 * Math.log10(rms);
  return Math.max(-60, Math.min(0, db));
}

export interface CaptureTrackView {
  id: string;
  label: string;
  status: Status;
  pill: string;
  detail: string;
}

const TRACKS = [
  { id: "gameplay_video", label: "Gameplay video" },
  { id: "game_audio", label: "Game audio" },
  { id: "mic_audio", label: "Mic audio" },
  { id: "webcam_video", label: "Webcam video" },
] as const;

export function captureTrackViews(input: {
  obsConnected: boolean;
  obsRecording: boolean;
  cameraLabel: string | null;
  micLive: boolean;
}): CaptureTrackView[] {
  return TRACKS.map((track) => {
    if (track.id === "mic_audio") {
      if (!input.micLive) return { ...track, status: "off", pill: "no device", detail: "no device" };
      return {
        ...track,
        status: "ok",
        pill: input.obsRecording ? "rec" : "live",
        detail: "microphone",
      };
    }
    if (track.id === "webcam_video") {
      if (!input.cameraLabel) return { ...track, status: "off", pill: "no device", detail: "no device" };
      return {
        ...track,
        status: "ok",
        pill: input.obsRecording ? "rec" : "live",
        detail: input.cameraLabel,
      };
    }
    if (!input.obsConnected) {
      return { ...track, status: "down", pill: "OBS not running", detail: "OBS not running" };
    }
    return {
      ...track,
      status: "ok",
      pill: input.obsRecording ? "rec" : "ready",
      detail: "OBS",
    };
  });
}

export function browserMedia(): MediaDevices | null {
  const candidate: unknown = Reflect.get(navigator, "mediaDevices");
  if (typeof candidate !== "object" || candidate === null) return null;
  if (!("enumerateDevices" in candidate) || !("getUserMedia" in candidate)) return null;
  if (typeof candidate.enumerateDevices !== "function" || typeof candidate.getUserMedia !== "function") {
    return null;
  }
  return candidate as MediaDevices;
}

export async function openObsbotPreview(): Promise<{ stream: MediaStream; label: string } | null> {
  const media = browserMedia();
  if (!media) return null;
  let devices: MediaDeviceInfo[];
  try {
    devices = await media.enumerateDevices();
  } catch {
    return null;
  }
  let choice = pickObsbotDevice(devices);
  if (!choice) {
    let probe: MediaStream | null = null;
    try {
      probe = await media.getUserMedia({ video: true, audio: false });
      devices = await media.enumerateDevices();
      choice = pickObsbotDevice(devices);
    } catch {
      choice = null;
    }
    const probeTrack = probe?.getVideoTracks()[0];
    const probeId = probeTrack?.getSettings().deviceId;
    const probeLabel = probeTrack?.label ?? "";
    if (probe && choice && (choice.deviceId === probeId || choice.label === probeLabel)) {
      return { stream: probe, label: choice.label || probeLabel };
    }
    probe?.getTracks().forEach((track) => {
      track.stop();
    });
    if (!choice) return null;
  }
  try {
    const stream = await media.getUserMedia({
      video: { deviceId: { exact: choice.deviceId } },
      audio: false,
    });
    const label = stream.getVideoTracks()[0]?.label || choice.label;
    return { stream, label };
  } catch {
    return null;
  }
}

import { useEffect, useState } from "react";

import { browserMedia, levelDbFromTimeDomain, openObsbotPreview } from "./devices";

export interface CaptureDevicesState {
  cameraLabel: string | null;
  cameraStream: MediaStream | null;
  micDb: number | null;
  micLive: boolean;
}

const IDLE: CaptureDevicesState = {
  cameraLabel: null,
  cameraStream: null,
  micDb: null,
  micLive: false,
};

function readAudioContext(): (new () => AudioContext) | null {
  const candidate: unknown = Reflect.get(window, "AudioContext");
  if (typeof candidate !== "function") return null;
  return candidate as new () => AudioContext;
}

function stopStream(stream: MediaStream | null): void {
  stream?.getTracks().forEach((track) => {
    track.stop();
  });
}

/** Live OBSBOT preview (getUserMedia by label) and a simple mic meter. */
export function useCaptureDevices(): CaptureDevicesState {
  const [state, setState] = useState<CaptureDevicesState>(IDLE);

  useEffect(() => {
    const gate = { open: true };
    const alive = (): boolean => gate.open;
    let camera: MediaStream | null = null;
    let mic: MediaStream | null = null;
    let audio: AudioContext | null = null;
    let timer = 0;

    const release = () => {
      gate.open = false;
      window.clearTimeout(timer);
      stopStream(camera);
      stopStream(mic);
      if (audio) void audio.close();
      camera = null;
      mic = null;
      audio = null;
    };

    const run = async () => {
      let preview: { stream: MediaStream; label: string } | null = null;
      try {
        preview = await openObsbotPreview();
      } catch {
        preview = null;
      }
      if (!alive()) {
        stopStream(preview?.stream ?? null);
        return;
      }
      if (preview) {
        camera = preview.stream;
        setState((prev) => ({ ...prev, cameraLabel: preview.label, cameraStream: preview.stream }));
      }
      const media = browserMedia();
      if (!media) return;
      try {
        mic = await media.getUserMedia({ audio: true, video: false });
      } catch {
        if (alive()) setState((prev) => ({ ...prev, micLive: false, micDb: null }));
        return;
      }
      if (!alive()) {
        stopStream(mic);
        return;
      }
      const Ctx = readAudioContext();
      if (!Ctx) {
        setState((prev) => ({ ...prev, micLive: false, micDb: null }));
        stopStream(mic);
        mic = null;
        return;
      }
      audio = new Ctx();
      const source = audio.createMediaStreamSource(mic);
      const analyser = audio.createAnalyser();
      analyser.fftSize = 1024;
      source.connect(analyser);
      const samples = new Uint8Array(analyser.fftSize);
      const tick = () => {
        if (!alive()) return;
        analyser.getByteTimeDomainData(samples);
        const micDb = levelDbFromTimeDomain(samples);
        setState((prev) => ({ ...prev, micLive: true, micDb }));
        timer = window.setTimeout(tick, 120);
      };
      tick();
    };

    void run();
    return () => {
      release();
    };
  }, []);

  return state;
}

/** Speak agent lines via Owl TTS (HTTP) or browser fallback. */

export interface SpeakOptions {
  voiceId?: string;
  rate?: number;
}

const owlBase = (): string | undefined => {
  const raw = import.meta.env.VITE_OWL_TTS_URL?.trim();
  return raw && raw.length > 0 ? raw.replace(/\/$/, "") : undefined;
};

/** POST JSON `{ text, voice }` → audio bytes (mp3/wav). Adapt URL to your Owl / OwlAI endpoint. */
async function speakViaOwl(text: string, voiceId: string): Promise<boolean> {
  const base = owlBase();
  if (!base) return false;
  const endpoints = [`${base}/api/tts`, `${base}/synthesize`, `${base}/v1/audio/speech`];
  for (const url of endpoints) {
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "audio/*" },
        body: JSON.stringify({ text, voice: voiceId, format: "mp3" }),
      });
      if (!res.ok) continue;
      const blob = await res.blob();
      if (blob.size === 0) continue;
      await playBlob(blob);
      return true;
    } catch {
      continue;
    }
  }
  return false;
}

function playBlob(blob: Blob): Promise<void> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.onended = () => {
      URL.revokeObjectURL(url);
      resolve();
    };
    audio.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("audio playback failed"));
    };
    void audio.play().catch(reject);
  });
}

export async function speakAgentLine(text: string, opts: SpeakOptions = {}): Promise<void> {
  const voiceId = opts.voiceId ?? "Onyx";
  if (await speakViaOwl(text, voiceId)) return;
  if (!("speechSynthesis" in window)) return;
  const utter = new SpeechSynthesisUtterance(text);
  utter.rate = opts.rate ?? 1.05;
  utter.pitch = 0.92;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utter);
}

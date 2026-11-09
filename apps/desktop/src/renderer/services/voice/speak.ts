/** Speak agent lines via Owlbox TTS (OpenAI-compatible HTTP) or browser fallback. */

export interface SpeakOptions {
  voiceId?: string;
  rate?: number;
}

export interface OwlboxAttempt {
  path: string;
  body: Record<string, unknown>;
}

const DEFAULT_OWL_PORT = 8790;

export function owlboxBaseUrl(): string | undefined {
  const raw = import.meta.env.VITE_OWL_TTS_URL?.trim();
  return raw && raw.length > 0 ? raw.replace(/\/$/, "") : undefined;
}

/** Request shapes for Owlbox / Voicebox OpenAI-compatible servers (port 8790 by default). */
export function owlboxSpeechAttempts(text: string, voiceId: string): OwlboxAttempt[] {
  return [
    {
      path: "/v1/audio/speech",
      body: {
        model: "tts",
        input: text,
        voice: voiceId,
        response_format: "mp3",
      },
    },
    {
      path: "/v1/audio/speech",
      body: {
        model: "tts",
        input: text,
        voice: voiceId,
        response_format: "wav",
      },
    },
    // Legacy Owl / custom endpoints kept as fallbacks.
    {
      path: "/api/tts",
      body: { text, voice: voiceId, format: "mp3" },
    },
    {
      path: "/synthesize",
      body: { text, voice: voiceId },
    },
  ];
}

export function defaultOwlboxUrl(): string {
  return `http://127.0.0.1:${DEFAULT_OWL_PORT}`;
}

async function speakViaOwlbox(text: string, voiceId: string): Promise<boolean> {
  const base = owlboxBaseUrl();
  if (!base) return false;
  for (const attempt of owlboxSpeechAttempts(text, voiceId)) {
    try {
      const res = await fetch(`${base}${attempt.path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "audio/*, application/octet-stream" },
        body: JSON.stringify(attempt.body),
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

function speakViaBrowser(text: string, rate: number): void {
  if (!("speechSynthesis" in window)) return;
  const utter = new SpeechSynthesisUtterance(text);
  utter.rate = rate;
  utter.pitch = 0.92;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utter);
}

export async function speakAgentLine(text: string, opts: SpeakOptions = {}): Promise<void> {
  const voiceId = opts.voiceId ?? "Onyx";
  const trimmed = text.trim();
  if (!trimmed) return;
  if (await speakViaOwlbox(trimmed, voiceId)) return;
  speakViaBrowser(trimmed, opts.rate ?? 1.05);
}

/** Serialize live crew lines so agents do not talk over each other. */
let speechQueue: Promise<void> = Promise.resolve();

export function enqueueAgentSpeech(text: string, opts: SpeakOptions = {}): Promise<void> {
  const run = speechQueue.then(() => speakAgentLine(text, opts)).catch(() => {
    /* keep queue alive after a failed line */
  });
  speechQueue = run;
  return run;
}

export function stripChatVoicePrefix(text: string): string {
  return text.replace(/^\[(?:banter|outcome(?: fail)?|lesson|discovery)\]\s*/i, "").trim();
}

export function shouldSpeakLiveAgentLine(text: string): boolean {
  return (
    text.startsWith("[banter]") ||
    text.startsWith("[outcome]") ||
    text.startsWith("[outcome fail]")
  );
}

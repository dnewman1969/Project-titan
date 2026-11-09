import { describe, expect, it } from "vitest";

import {
  owlboxSpeechAttempts,
  shouldSpeakLiveAgentLine,
  stripChatVoicePrefix,
} from "../../src/renderer/services/voice/speak";

describe("Owlbox TTS helpers", () => {
  it("builds OpenAI-compatible speech attempts first", () => {
    const attempts = owlboxSpeechAttempts("Orbit achieved.", "Onyx");
    expect(attempts[0]?.path).toBe("/v1/audio/speech");
    expect(attempts[0]?.body).toMatchObject({
      model: "tts",
      input: "Orbit achieved.",
      voice: "Onyx",
      response_format: "mp3",
    });
  });

  it("strips live chat voice prefixes", () => {
    expect(stripChatVoicePrefix("[banter] I solved that.")).toBe("I solved that.");
    expect(stripChatVoicePrefix("[outcome fail] Missed the burn.")).toBe("Missed the burn.");
  });

  it("only speaks banter and outcomes live", () => {
    expect(shouldSpeakLiveAgentLine("[banter] Hello")).toBe(true);
    expect(shouldSpeakLiveAgentLine("[outcome] Done")).toBe(true);
    expect(shouldSpeakLiveAgentLine("[lesson] Remember staging")).toBe(false);
    expect(shouldSpeakLiveAgentLine("plain demo line")).toBe(false);
  });
});

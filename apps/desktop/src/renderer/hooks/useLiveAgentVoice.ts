import { useEffect, useRef } from "react";

import type { AppDispatch } from "../app/store";
import { useAppDispatch, useAppSelector } from "../app/hooks";
import { setSpeaking } from "../features/agents/agentsChatSlice";
import { OWL_VOICE_BY_ROLE } from "../features/agents/arrogantLines";
import {
  shouldSpeakLiveAgentLine,
  speakAgentLine,
  stripChatVoicePrefix,
} from "../services/voice/speak";

/**
 * Speak live session agent lines (banter / play outcomes) through Owlbox TTS.
 * Demo Brag/Roast buttons keep using speakAgentLine directly in AgentsPanel.
 */
export function useLiveAgentVoice(): void {
  const dispatch = useAppDispatch();
  const sessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const lines = useAppSelector((s) => s.agentsChat.lines);
  const spoken = useRef(new Set<string>());

  useEffect(() => {
    spoken.current.clear();
  }, [sessionId]);

  useEffect(() => {
    if (!sessionId) return;
    for (const line of lines) {
      if (spoken.current.has(line.id)) continue;
      spoken.current.add(line.id);
      if (!shouldSpeakLiveAgentLine(line.text)) continue;
      const body = stripChatVoicePrefix(line.text);
      if (!body) continue;
      const voiceId = OWL_VOICE_BY_ROLE[line.role] ?? "Onyx";
      void speakLiveLine(dispatch, line.persona_slug, body, voiceId);
    }
  }, [dispatch, lines, sessionId]);
}

function speakLiveLine(
  dispatch: AppDispatch,
  personaSlug: string,
  body: string,
  voiceId: string,
): Promise<void> {
  return enqueueLiveSpeechJob(async () => {
    dispatch(setSpeaking(personaSlug));
    try {
      await speakAgentLine(body, { voiceId });
    } finally {
      dispatch(setSpeaking(null));
    }
  });
}

/** Ordered queue so live crew lines do not talk over each other. */
let liveSpeechQueue: Promise<void> = Promise.resolve();

function enqueueLiveSpeechJob(job: () => Promise<void>): Promise<void> {
  const run = liveSpeechQueue.then(job).catch(() => {
    /* keep queue alive after a failed utterance */
  });
  liveSpeechQueue = run;
  return run;
}

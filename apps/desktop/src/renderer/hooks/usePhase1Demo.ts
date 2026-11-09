import { useEffect, useRef, type MutableRefObject } from "react";

import { useCreateSessionMutation, useGetHealthQuery, useStartSessionMutation } from "../app/api";
import { useAppDispatch, useAppSelector } from "../app/hooks";
import { getTitan } from "../app/runtime";
import { agentSaid, setSpeaking } from "../features/agents/agentsChatSlice";
import {
  OWL_VOICE_BY_ROLE,
  DEMO_ROSTER,
  pickBanterLine,
  type RosterEntry,
} from "../features/agents/arrogantLines";
import { autoDemoEnabled } from "../app/viteEnv";
import { showNotice } from "../features/operations/layoutSlice";
import { setActiveSession } from "../features/sessions/sessionsSlice";
import { speakAgentLine } from "../services/voice/speak";

const AUTO_DEMO = autoDemoEnabled();

async function deliverGreeting(
  dispatch: ReturnType<typeof useAppDispatch>,
  busyRef: MutableRefObject<boolean>,
): Promise<void> {
  const wernher: RosterEntry = DEMO_ROSTER.find((a) => a.role === "director") ??
    DEMO_ROSTER[0] ?? {
      persona_slug: "wernher",
      display_name: "Wernher",
      role: "director",
    };
  if (busyRef.current) return;
  const text = pickBanterLine("greeting", wernher);
  const body = text.includes(": ") ? text.split(": ").slice(1).join(": ") : text;
  busyRef.current = true;
  dispatch(
    agentSaid({
      persona_slug: wernher.persona_slug,
      display_name: wernher.display_name,
      role: wernher.role,
      text: body,
    }),
  );
  dispatch(setSpeaking(wernher.persona_slug));
  try {
    await speakAgentLine(body, { voiceId: OWL_VOICE_BY_ROLE[wernher.role] ?? "Onyx" });
  } finally {
    dispatch(setSpeaking(null));
    busyRef.current = false;
  }
}

/** When VITE_TITAN_AUTO_DEMO=1: live session + fixture telemetry + Director greeting (no Kerbal required). */
export function usePhase1Demo(): void {
  const dispatch = useAppDispatch();
  const activeId = useAppSelector((s) => s.sessions.activeSessionId);
  const { backend } = getTitan();
  const bootstrapped = useRef(false);
  const greeted = useRef(false);
  const voiceBusy = useRef(false);
  const { data: health } = useGetHealthQuery(undefined, { skip: backend === "none" || !AUTO_DEMO });
  const [createSession] = useCreateSessionMutation();
  const [startSession] = useStartSessionMutation();

  useEffect(() => {
    if (typeof localStorage !== "undefined" && localStorage.getItem("titan.skipAutoDemo") === "1") {
      return;
    }
    if (!AUTO_DEMO || backend === "none" || bootstrapped.current || activeId || !health) return;
    bootstrapped.current = true;
    void (async () => {
      const title = "Demo - no game required";
      const created = await createSession({
        game_slug: "ksp",
        title,
        mode: "observe",
        settings: { agents_enabled: true, demo_telemetry: true, play_enabled: true },
      });
      if (!("data" in created) || !created.data) {
        dispatch(showNotice("Demo session could not start — check Redis/Postgres in the boot splash."));
        bootstrapped.current = false;
        return;
      }
      const started = await startSession({ sessionId: created.data.id });
      if ("data" in started && started.data) {
        dispatch(
          setActiveSession({
            id: started.data.id,
            title: started.data.title?.trim() || title,
            sessionSource: "fixture",
            playEnabled: true,
          }),
        );
        dispatch(showNotice("Demo session live - fixture telemetry driving the bar; crew is listening."));
      }
    })();
  }, [activeId, backend, createSession, dispatch, health, startSession]);

  useEffect(() => {
    if (!AUTO_DEMO || !activeId || greeted.current) return;
    greeted.current = true;
    const t = window.setTimeout(() => {
      void deliverGreeting(dispatch, voiceBusy);
    }, 2500);
    return () => {
      clearTimeout(t);
    };
  }, [activeId, dispatch]);
}

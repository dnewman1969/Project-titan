import { useEffect } from "react";

import { useLazyGetPlayReadinessQuery } from "../app/api";
import { useAppDispatch, useAppSelector } from "../app/hooks";
import { setPlayAttach, type PlayBackendKind } from "../features/sessions/sessionsSlice";

const POLL_MS = 15_000;

/** Refresh live kRPC/SCS readiness while a live session has agent play enabled. */
export function usePlayAttachSync(): void {
  const dispatch = useAppDispatch();
  const sessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const sessionSource = useAppSelector((s) => s.sessions.sessionSource);
  const playEnabled = useAppSelector((s) => s.sessions.playEnabled);
  const gameSlug = useAppSelector((s) => s.sessions.activeGameSlug);
  const [fetchReadiness] = useLazyGetPlayReadinessQuery();

  useEffect(() => {
    if (!sessionId || sessionSource !== "live" || !playEnabled || !gameSlug) {
      return;
    }
    let cancelled = false;
    const poll = async () => {
      const result = await fetchReadiness({ gameSlug, source: "live" }, true);
      if (cancelled || !("data" in result) || !result.data?.play_attach) {
        return;
      }
      const attach = result.data.play_attach;
      const backend = attach.backend as PlayBackendKind;
      dispatch(
        setPlayAttach({
          playReady: attach.ready,
          playAttachMessage: attach.message,
          playBackend: backend === "auto" ? null : backend,
        }),
      );
    };
    void poll();
    const timer = window.setInterval(() => {
      void poll();
    }, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [dispatch, fetchReadiness, gameSlug, playEnabled, sessionId, sessionSource]);
}

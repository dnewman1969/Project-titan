import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import { useEffect, useRef, useState } from "react";

import type { GameViewStatus } from "../../../shared/ipc";

import { useAppSelector } from "../../app/hooks";
import { getTitan } from "../../app/runtime";

function exeFile(exe: string | null): string {
  if (!exe) return "";
  const parts = exe.split(/[/\\]/);
  return parts[parts.length - 1] ?? "";
}

export function gameLabel(slug: string | null): string {
  if (slug === "ksp") return "Kerbal Space Program";
  if (slug === "ets2") return "Euro Truck Simulator 2";
  if (slug === "ats") return "American Truck Simulator";
  return "the game";
}

export function useGameViewStatus(): GameViewStatus | null {
  const [status, setStatus] = useState<GameViewStatus | null>(null);
  useEffect(() => {
    let liveEffect = true;
    void getTitan()
      .getGameViewStatus()
      .then((next) => {
        if (liveEffect) setStatus(next);
      });
    const unsubscribe = getTitan().onGameViewStatus((next) => {
      if (liveEffect) setStatus(next);
    });
    return () => {
      liveEffect = false;
      unsubscribe();
    };
  }, []);
  return status;
}

function holeCopy(input: {
  sessionId: string | null;
  fixture: boolean;
  live: boolean;
  status: GameViewStatus | null;
  gameSlug: string | null;
}): { title: string; body: string } | null {
  if (!input.sessionId) {
    return { title: "No session.", body: "File → New session." };
  }
  if (input.fixture) {
    return {
      title: "Fixture session.",
      body: "Demo telemetry only. Register a game install (View → Game discovery), then File → New session with that profile for a live attach.",
    };
  }
  if (input.status?.attached) return null;
  const reason = input.status?.reason?.trim();
  if (reason) {
    const retry = /fail|reject|could not|fell back/i.test(reason);
    return {
      title: reason,
      body: retry ? "Trying again." : "The game has not locked into this monitor yet.",
    };
  }
  return {
    title: `Looking for ${gameLabel(input.gameSlug)}.`,
    body: "The game has not locked into this monitor yet.",
  };
}

/**
 * The program monitor. The hole under the header is the only rectangle sent to the game view.
 * A fixture or an empty session does not dock a window over the slate.
 */
export function GameWindow() {
  const sessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const sessionSource = useAppSelector((s) => s.sessions.sessionSource);
  const playEnabled = useAppSelector((s) => s.sessions.playEnabled);
  const playBackend = useAppSelector((s) => s.sessions.playBackend);
  const playReady = useAppSelector((s) => s.sessions.playReady);
  const playAttachMessage = useAppSelector((s) => s.sessions.playAttachMessage);
  const gameSlug = useAppSelector((s) => s.sessions.activeGameSlug);
  const gamePid = useAppSelector((s) => s.sessions.gamePid);
  const modalOpen = useAppSelector((s) => {
    const boot =
      getTitan().backend === "managed" &&
      !s.supervisor.splashDismissed &&
      s.supervisor.status?.ready !== true;
    return (
      boot ||
      s.layout.aboutOpen ||
      s.layout.firstRunOpen ||
      s.layout.publishOpen ||
      s.layout.memoryBrowserOpen ||
      s.layout.gamesOpen ||
      s.layout.panels.events ||
      s.sessions.dialog !== null
    );
  });
  const status = useGameViewStatus();
  const holeRef = useRef<HTMLDivElement>(null);
  const fixture = sessionSource === "fixture";
  const live = sessionSource === "live";
  const dock = Boolean(sessionId) && live;
  const copy = holeCopy({ sessionId, fixture, live, status, gameSlug });
  const headerName = status?.attached
    ? status.title?.trim() || exeFile(status.exe) || gameLabel(gameSlug)
    : gameLabel(gameSlug);
  const headerPlace = status?.attached ? (status.mode === "embed" ? "embedded" : "in view") : null;

  useEffect(() => {
    getTitan().gameViewConfigure({ gameSlug, pid: gamePid });
  }, [gamePid, gameSlug]);

  useEffect(() => {
    getTitan().gameViewHold("modal", modalOpen);
  }, [modalOpen]);

  useEffect(() => {
    getTitan().gameViewHold("nodock", !dock);
  }, [dock]);

  useEffect(() => {
    return () => {
      getTitan().gameViewHold("modal", false);
      getTitan().gameViewHold("nodock", true);
    };
  }, []);

  useEffect(() => {
    const el = holeRef.current;
    if (!el || !dock) {
      getTitan().gameViewSync({ x: 0, y: 0, width: 0, height: 0 });
      return;
    }
    let frame = 0;
    const send = () => {
      const rect = el.getBoundingClientRect();
      getTitan().gameViewSync({ x: rect.left, y: rect.top, width: rect.width, height: rect.height });
    };
    send();
    const observer =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(() => {
            cancelAnimationFrame(frame);
            frame = requestAnimationFrame(send);
          });
    observer?.observe(el);
    window.addEventListener("resize", send);
    return () => {
      cancelAnimationFrame(frame);
      observer?.disconnect();
      window.removeEventListener("resize", send);
    };
  }, [dock]);

  return (
    <Paper
      component="section"
      aria-label="Program"
      variant="outlined"
      sx={{
        gridArea: "program",
        minWidth: 0,
        minHeight: 160,
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        border: "1px solid #8ea0b8",
        background:
          "radial-gradient(1200px 500px at 50% 120%, rgba(94,194,255,0.10), transparent 60%), radial-gradient(800px 400px at 10% -20%, rgba(169,139,255,0.10), transparent 60%), #121722",
      }}
    >
      <Box
        sx={{
          display: "flex",
          gap: 1,
          alignItems: "baseline",
          px: 1.25,
          py: 0.75,
          flex: "0 0 auto",
          borderBottom: "1px solid #8ea0b8",
        }}
      >
        <Typography variant="overline" color="text.secondary">
          PROGRAM
        </Typography>
        <Typography variant="body2" noWrap sx={{ minWidth: 0 }}>
          {headerName}
          {headerPlace ? ` · ${headerPlace}` : ""}
        </Typography>
        {playEnabled ? (
          <Typography variant="caption" color="text.secondary" sx={{ ml: "auto" }}>
            Play {playBackend ?? "on"}
          </Typography>
        ) : null}
      </Box>
      {sessionId && live && playAttachMessage ? (
        <Alert
          severity={playReady === false ? "warning" : "success"}
          variant="outlined"
          sx={{ mx: 1.25, mt: 0.75, flex: "0 0 auto" }}
        >
          {playReady === false ? (
            <>
              <strong>Live play waiting on game/mod.</strong> {playAttachMessage}
            </>
          ) : (
            <>Live install ready. {playAttachMessage}</>
          )}
        </Alert>
      ) : null}
      <Box
        ref={holeRef}
        data-testid="game-viewport"
        onPointerDown={() => {
          if (status?.attached) getTitan().gameViewFocus();
        }}
        sx={{
          flex: "1 1 auto",
          minHeight: 120,
          position: "relative",
          display: "grid",
          placeItems: "center",
          m: 1,
          borderRadius: 1,
          border: "1px solid rgba(142, 160, 184, 0.45)",
          bgcolor: "#0d1119",
        }}
      >
        {copy ? (
          <Box sx={{ textAlign: "center", maxWidth: 520, px: 3 }}>
            <Typography variant="h6">{copy.title}</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              {copy.body}
            </Typography>
          </Box>
        ) : null}
      </Box>
    </Paper>
  );
}

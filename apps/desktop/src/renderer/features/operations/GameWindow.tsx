import SportsEsportsOutlinedIcon from "@mui/icons-material/SportsEsportsOutlined";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
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

function statusLine(status: GameViewStatus | null, platform: string): string | null {
  if (status?.attached) {
    const name = status.title?.trim() || exeFile(status.exe) || "Game";
    return status.mode === "embed" ? `${name} · embedded` : `${name} · in view`;
  }
  if (status?.reason) return status.reason;
  if (platform === "win32") return "Looking for the game window";
  return null;
}

/**
 * The hero preview. On Windows the running game is locked to this rectangle
 * (borderless owned window for Unity/KSP; SetParent only when that stays reliable).
 */
export function GameWindow() {
  const sessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const sessionSource = useAppSelector((s) => s.sessions.sessionSource);
  const playEnabled = useAppSelector((s) => s.sessions.playEnabled);
  const playBackend = useAppSelector((s) => s.sessions.playBackend);
  const playReady = useAppSelector((s) => s.sessions.playReady);
  const playAttachMessage = useAppSelector((s) => s.sessions.playAttachMessage);
  const activeTitle = useAppSelector((s) => s.sessions.activeTitle);
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
      s.sessions.dialog !== null
    );
  });
  const [status, setStatus] = useState<GameViewStatus | null>(null);
  const holeRef = useRef<HTMLDivElement>(null);
  const platform = getTitan().platform;
  const fixture = sessionSource === "fixture";
  const live = sessionSource === "live";
  const line = statusLine(status, platform);

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

  useEffect(() => {
    getTitan().gameViewConfigure({ gameSlug, pid: gamePid });
  }, [gamePid, gameSlug]);

  useEffect(() => {
    getTitan().gameViewHold("modal", modalOpen);
  }, [modalOpen]);

  useEffect(() => {
    return () => {
      getTitan().gameViewHold("modal", false);
    };
  }, []);

  useEffect(() => {
    const el = holeRef.current;
    if (!el) return;
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
  }, []);

  return (
    <Paper
      component="section"
      aria-label="Game window"
      variant="outlined"
      sx={{
        gridArea: "game",
        minWidth: 0,
        minHeight: 0,
        height: "100%",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        background:
          "radial-gradient(1200px 500px at 50% 120%, rgba(94,194,255,0.10), transparent 60%), radial-gradient(800px 400px at 10% -20%, rgba(169,139,255,0.10), transparent 60%), #0d1119",
      }}
    >
      <Box
        sx={{
          display: "flex",
          gap: 1,
          flexWrap: "wrap",
          alignItems: "center",
          px: 1.25,
          py: 0.75,
          flex: "0 0 auto",
        }}
      >
        <Chip size="small" label={activeTitle ? `Session: ${activeTitle}` : "Scene: none"} />
        {sessionSource ? (
          <Chip
            size="small"
            color={live ? (playEnabled && playReady === false ? "warning" : "success") : "default"}
            label={live ? "Live install" : "Fixture telemetry"}
          />
        ) : (
          <Chip size="small" label="Mission: none" />
        )}
        {playEnabled ? <Chip size="small" color="primary" label={`Play: ${playBackend ?? "on"}`} /> : null}
        {line ? (
          <Chip
            size="small"
            color={status?.attached ? "success" : "default"}
            variant="outlined"
            label={line}
          />
        ) : null}
        <Box sx={{ flex: 1 }} />
        {status?.attached ? (
          <Button
            size="small"
            onClick={() => {
              getTitan().gameViewFocus();
            }}
          >
            Focus game
          </Button>
        ) : null}
      </Box>
      {sessionId && fixture ? (
        <Alert severity="info" variant="outlined" sx={{ mx: 1.25, mb: 0.75, flex: "0 0 auto" }}>
          Fixture mode — demo telemetry only. Register a game install (View → Game discovery), then File → New
          session with that profile for live kRPC/SCS attach
          {playEnabled ? " (current play is software HIL)." : "."}
        </Alert>
      ) : null}
      {sessionId && live && playAttachMessage ? (
        <Alert
          severity={playReady === false ? "warning" : "success"}
          variant="outlined"
          sx={{ mx: 1.25, mb: 0.75, flex: "0 0 auto" }}
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
          getTitan().gameViewFocus();
        }}
        sx={{
          flex: "1 1 auto",
          minHeight: 0,
          position: "relative",
          display: "grid",
          placeItems: "center",
        }}
      >
        <Box sx={{ textAlign: "center", maxWidth: 520, px: 3 }}>
          <SportsEsportsOutlinedIcon sx={{ fontSize: 56, color: "text.disabled" }} />
          <Typography variant="h6" sx={{ mt: 1 }}>
            {sessionId ? (live ? "Live session" : "Fixture session") : "No game running"}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
            This is the live game view. On Windows, Kerbal Space Program locks into this rectangle while it
            runs. ETS2 and ATS use the same frame.
          </Typography>
        </Box>
      </Box>
    </Paper>
  );
}

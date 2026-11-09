import SportsEsportsOutlinedIcon from "@mui/icons-material/SportsEsportsOutlined";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";

import { useAppSelector } from "../../app/hooks";

/** Placeholder for the desktopCapturer game preview (D11, M7.T1). Display only, never recorded. */
export function GameWindow() {
  const sessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const sessionSource = useAppSelector((s) => s.sessions.sessionSource);
  const playEnabled = useAppSelector((s) => s.sessions.playEnabled);
  const playBackend = useAppSelector((s) => s.sessions.playBackend);
  const playReady = useAppSelector((s) => s.sessions.playReady);
  const playAttachMessage = useAppSelector((s) => s.sessions.playAttachMessage);
  const activeTitle = useAppSelector((s) => s.sessions.activeTitle);

  const fixture = sessionSource === "fixture";
  const live = sessionSource === "live";

  return (
    <Paper
      component="section"
      aria-label="Game window"
      variant="outlined"
      sx={{
        gridArea: "game",
        position: "relative",
        minHeight: 0,
        overflow: "hidden",
        display: "grid",
        placeItems: "center",
        background:
          "radial-gradient(1200px 500px at 50% 120%, rgba(94,194,255,0.10), transparent 60%), radial-gradient(800px 400px at 10% -20%, rgba(169,139,255,0.10), transparent 60%), #0d1119",
      }}
    >
      <Box
        sx={{ position: "absolute", top: 12, left: 12, right: 12, display: "flex", gap: 1, flexWrap: "wrap" }}
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
      </Box>
      {sessionId && fixture ? (
        <Alert
          severity="info"
          variant="outlined"
          sx={{ position: "absolute", top: 52, left: 12, right: 12, zIndex: 1 }}
        >
          Fixture mode — demo telemetry only. Register a game install (View → Games), then File → New session
          with that profile for live kRPC/SCS attach
          {playEnabled ? " (current play is software HIL)." : "."}
        </Alert>
      ) : null}
      {sessionId && live && playAttachMessage ? (
        <Alert
          severity={playReady === false ? "warning" : "success"}
          variant="outlined"
          sx={{ position: "absolute", top: 52, left: 12, right: 12, zIndex: 1 }}
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
      <Box sx={{ textAlign: "center", maxWidth: 420, px: 2 }}>
        <SportsEsportsOutlinedIcon sx={{ fontSize: 56, color: "text.disabled" }} />
        <Typography variant="h6" sx={{ mt: 1 }}>
          {sessionId ? (live ? "Live session" : "Fixture session") : "No game running"}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          {sessionId
            ? "The live game preview appears here when desktop capture is available. Learn-loop outcomes show in AI Agents."
            : "The live game preview appears here when a session starts. Scene, mission and event toasts overlay it."}
        </Typography>
      </Box>
    </Paper>
  );
}

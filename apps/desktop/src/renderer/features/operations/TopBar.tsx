import PowerSettingsNewIcon from "@mui/icons-material/PowerSettingsNew";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import FormControlLabel from "@mui/material/FormControlLabel";
import Switch from "@mui/material/Switch";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { useCallback } from "react";

import { useSetSessionPlayMutation } from "../../app/api";
import { formatApiError } from "../../app/formatApiError";
import { useAppDispatch, useAppSelector } from "../../app/hooks";
import { getTitan } from "../../app/runtime";
import { engageKill } from "../safety/engageKill";
import { useContractSessionLine } from "../learn/LearnFeedbackStrip";
import { gameLabel } from "./GameWindow";
import { setSessionBarError, showNotice } from "./layoutSlice";
import { setPlayEnabled, type PlayBackendKind } from "../sessions/sessionsSlice";

function sourceLabel(source: "live" | "fixture" | null): string | null {
  if (source === "live") return "Live";
  if (source === "fixture") return "Fixture";
  return null;
}

/** Session bar. Record lives on the program transport, not here. */
export function SessionBar() {
  const dispatch = useAppDispatch();
  const [setSessionPlay, { isLoading: playToggling }] = useSetSessionPlayMutation();
  const activeSessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const activeTitle = useAppSelector((s) => s.sessions.activeTitle);
  const gameSlug = useAppSelector((s) => s.sessions.activeGameSlug);
  const sessionSource = useAppSelector((s) => s.sessions.sessionSource);
  const playEnabled = useAppSelector((s) => s.sessions.playEnabled);
  const playBackend = useAppSelector((s) => s.sessions.playBackend);
  const sessionBarError = useAppSelector((s) => s.layout.sessionBarError);
  const contractLine = useContractSessionLine();
  const { killHotkey } = getTitan();
  const source = sourceLabel(sessionSource);

  const togglePlay = useCallback(async () => {
    if (!activeSessionId) {
      dispatch(showNotice("Create a live session first (File → New session)."));
      dispatch(setSessionBarError("No session. File → New session."));
      return;
    }
    const next = !playEnabled;
    const result = await setSessionPlay({ sessionId: activeSessionId, enabled: next });
    if ("data" in result && result.data) {
      const attachRaw = Reflect.get(result.data, "play_attach");
      const attach =
        typeof attachRaw === "object" && attachRaw !== null
          ? (attachRaw as { backend?: string; ready?: boolean; message?: string })
          : null;
      dispatch(
        setPlayEnabled({
          playEnabled: next,
          playBackend: (attach?.backend as PlayBackendKind | undefined) ?? (next ? "hil" : null),
          playReady: typeof attach?.ready === "boolean" ? attach.ready : null,
          playAttachMessage: typeof attach?.message === "string" ? attach.message : null,
        }),
      );
      dispatch(setSessionBarError(null));
      dispatch(
        showNotice(
          next
            ? `Agent play on (${attach?.backend ?? "hil"})${attach?.message ? ` — ${attach.message}` : ""}`
            : "Agent play off — actions worker detached.",
        ),
      );
      return;
    }
    const message = formatApiError(result.error);
    dispatch(setSessionBarError(message));
    dispatch(showNotice(`Could not toggle play: ${message}`));
  }, [activeSessionId, dispatch, playEnabled, setSessionPlay]);

  return (
    <Box
      component="header"
      aria-label="Session bar"
      sx={{
        gridArea: "session",
        display: "flex",
        alignItems: "center",
        flexWrap: "wrap",
        gap: 1.25,
        px: 1.5,
        py: 0.75,
        minHeight: 48,
        borderRadius: 2,
        bgcolor: "background.paper",
        border: 1,
        borderColor: "divider",
      }}
    >
      <Typography variant="h6" component="h1" sx={{ fontSize: 15, letterSpacing: 3 }}>
        TITAN
      </Typography>
      <Typography variant="body2">{activeSessionId ? gameLabel(gameSlug) : "No session"}</Typography>
      <Typography variant="body2" color="text.secondary" noWrap sx={{ maxWidth: 280 }}>
        {activeTitle ?? "File → New session"}
      </Typography>
      {source ? (
        <Typography variant="body2" color={source === "Live" ? "success.main" : "text.secondary"}>
          {source}
        </Typography>
      ) : null}
      {contractLine ? (
        <Typography variant="body2" sx={{ minWidth: 0 }} noWrap>
          {contractLine}
        </Typography>
      ) : null}
      <FormControlLabel
        sx={{ ml: 0.5, mr: 0 }}
        control={
          <Switch
            size="small"
            checked={playEnabled}
            disabled={!activeSessionId || playToggling}
            onChange={() => {
              void togglePlay();
            }}
            slotProps={{ input: { "aria-label": "Toggle agent play" } }}
          />
        }
        label={
          <Typography variant="caption" color="text.secondary">
            {playEnabled && playBackend ? `Agent play (${playBackend})` : "Agent play"}
          </Typography>
        }
      />
      {sessionBarError ? (
        <Typography variant="caption" color="error" sx={{ minWidth: 0 }}>
          {sessionBarError}
        </Typography>
      ) : null}
      <Box sx={{ flex: 1 }} />
      <Tooltip title={`Kill switch (${killHotkey}). Stops all AI control.`}>
        <Button
          variant="contained"
          color="error"
          size="small"
          startIcon={<PowerSettingsNewIcon />}
          onClick={() => {
            engageKill(dispatch);
          }}
          sx={{ fontWeight: 800, letterSpacing: 1.5, px: 2 }}
        >
          KILL
        </Button>
      </Tooltip>
    </Box>
  );
}

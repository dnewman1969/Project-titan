import FiberManualRecordIcon from "@mui/icons-material/FiberManualRecord";
import PowerSettingsNewIcon from "@mui/icons-material/PowerSettingsNew";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { MONO_FONT, StatusPill } from "@titan/ui-kit";
import { useCallback, useEffect } from "react";

import {
  useKillMutation,
  useStartRecordingMutation,
  useStopRecordingMutation,
  useStopSessionMutation,
} from "../../app/api";
import { useAppDispatch, useAppSelector } from "../../app/hooks";
import { getTitan } from "../../app/runtime";
import type { ApiStatus } from "../../app/useApiStatus";
import { triggerKill } from "../../app/useShellBridge";
import { showNotice } from "./layoutSlice";
import {
  clearRecordingMenuRequest,
  setRecordingActive,
  setRecordingRootDir,
} from "../sessions/sessionsSlice";

export function TopBar({ status }: { status: ApiStatus }) {
  const dispatch = useAppDispatch();
  const [kill] = useKillMutation();
  const [stopSession] = useStopSessionMutation();
  const [startRec] = useStartRecordingMutation();
  const [stopRec] = useStopRecordingMutation();
  const activeSessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const activeTitle = useAppSelector((s) => s.sessions.activeTitle);
  const sessionSource = useAppSelector((s) => s.sessions.sessionSource);
  const playEnabled = useAppSelector((s) => s.sessions.playEnabled);
  const recordingActive = useAppSelector((s) => s.sessions.recordingActive);
  const recordingMenuRequest = useAppSelector((s) => s.sessions.recordingMenuRequest);
  const { killHotkey, backend } = getTitan();

  const toggleRecording = useCallback(async () => {
    if (!activeSessionId) {
      dispatch(showNotice("Create a live session first (Session → New session)."));
      return;
    }
    if (recordingActive) {
      const result = await stopRec(activeSessionId);
      if ("data" in result && result.data) {
        dispatch(setRecordingActive(false));
        dispatch(showNotice("Recording stopped."));
      } else {
        dispatch(showNotice("Could not stop recording — see API logs."));
      }
      return;
    }
    const result = await startRec(activeSessionId);
    if ("data" in result && result.data) {
      dispatch(setRecordingActive(true));
      dispatch(setRecordingRootDir(result.data.root_dir ?? null));
      dispatch(showNotice("Recording started (OBS optional — manifest still written)."));
    } else {
      dispatch(showNotice("Could not start recording — need a live session."));
    }
  }, [activeSessionId, dispatch, recordingActive, startRec, stopRec]);

  useEffect(() => {
    if (!recordingMenuRequest) return;
    const wantStart = recordingMenuRequest === "start";
    if (wantStart === recordingActive) {
      dispatch(clearRecordingMenuRequest());
      return;
    }
    void toggleRecording().finally(() => {
      dispatch(clearRecordingMenuRequest());
    });
  }, [dispatch, recordingActive, recordingMenuRequest, toggleRecording]);

  return (
    <Box
      component="header"
      aria-label="Titan status bar"
      sx={{
        gridArea: "top",
        display: "flex",
        alignItems: "center",
        gap: 1.5,
        px: 1.5,
        py: 0.75,
        borderRadius: 2,
        bgcolor: "background.paper",
        border: 1,
        borderColor: "divider",
      }}
    >
      <Box
        aria-hidden
        sx={{
          width: 22,
          height: 22,
          borderRadius: 1,
          background: "linear-gradient(135deg, #5ec2ff 0%, #a98bff 100%)",
          boxShadow: "0 0 12px rgba(94,194,255,0.35)",
        }}
      />
      <Typography variant="h6" component="h1" sx={{ fontSize: 15, letterSpacing: 3 }}>
        TITAN
      </Typography>
      <Typography variant="body2" color="text.secondary">
        Operations Center
      </Typography>
      <Chip
        size="small"
        variant={activeSessionId ? "filled" : "outlined"}
        color={activeSessionId ? "primary" : "default"}
        label={activeTitle ?? "No session"}
        sx={{ ml: 1, maxWidth: 220 }}
      />
      {activeSessionId && sessionSource ? (
        <Chip
          size="small"
          variant="outlined"
          color={sessionSource === "live" ? "success" : "default"}
          label={
            sessionSource === "live"
              ? playEnabled
                ? "Live + play"
                : "Live install"
              : playEnabled
                ? "Fixture + HIL play"
                : "Fixture telemetry"
          }
          sx={{ maxWidth: 160 }}
        />
      ) : null}
      <Box sx={{ flex: 1 }} />
      <StatusPill
        status={status.api}
        label="API"
        detail={status.apiDetail}
        pulse={status.api === "unknown"}
      />
      <StatusPill status={status.postgres} label="Database" detail={status.postgresDetail} />
      <StatusPill status={status.services} label="Services" detail={status.servicesDetail} />
      <Tooltip
        title={
          activeSessionId
            ? recordingActive
              ? "Stop session recording"
              : "Start session recording (writes manifest; OBS improves quality)"
            : "Start a session first"
        }
      >
        <Box
          role="status"
          aria-label={recordingActive ? "Recording: active" : "Recording: idle"}
          sx={{
            display: "flex",
            alignItems: "center",
            gap: 0.5,
            px: 0.5,
            color: recordingActive ? "error.main" : "text.secondary",
          }}
        >
          <IconButton
            size="small"
            color={recordingActive ? "error" : "default"}
            disabled={!activeSessionId || backend === "none"}
            onClick={() => void toggleRecording()}
            aria-label={recordingActive ? "Stop recording" : "Start recording"}
          >
            <FiberManualRecordIcon sx={{ fontSize: 16 }} />
          </IconButton>
          <Typography variant="caption" sx={{ fontFamily: MONO_FONT, fontWeight: 700 }}>
            {recordingActive ? "REC ON" : "REC"}
          </Typography>
        </Box>
      </Tooltip>
      <Tooltip title={`Kill switch (${killHotkey}). Stops all AI control.`}>
        <Button
          variant="contained"
          color="error"
          size="small"
          startIcon={<PowerSettingsNewIcon />}
          onClick={() => {
            const at = new Date().toISOString();
            const sid = activeSessionId;
            triggerKill(dispatch, { source: "button", at });
            if (backend !== "none") {
              if (sid) {
                void stopSession({ sessionId: sid, outcome: "aborted" });
              }
              void kill("button");
            }
          }}
          sx={{ fontWeight: 800, letterSpacing: 1.5, px: 2 }}
        >
          KILL
        </Button>
      </Tooltip>
    </Box>
  );
}

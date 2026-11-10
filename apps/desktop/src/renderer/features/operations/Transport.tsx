import FolderOpenIcon from "@mui/icons-material/FolderOpen";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import { MONO_FONT } from "@titan/ui-kit";
import { useCallback, useEffect, useState } from "react";

import { useStartRecordingMutation, useStopRecordingMutation } from "../../app/api";
import { formatApiError } from "../../app/formatApiError";
import { useAppDispatch, useAppSelector } from "../../app/hooks";
import { getTitan } from "../../app/runtime";
import type { ApiStatus } from "../../app/useApiStatus";
import { logEvent } from "../events/eventsSlice";
import { setTransportError, showNotice } from "./layoutSlice";
import { useGameViewStatus } from "./GameWindow";
import {
  clearRecordingMenuRequest,
  setRecordingActive,
  setRecordingRootDir,
} from "../sessions/sessionsSlice";

export function formatRecordingClock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  return [hours, minutes, seconds].map((part) => part.toString().padStart(2, "0")).join(":");
}

function idleNote(input: {
  sessionId: string | null;
  backend: string;
  obs: ApiStatus["obs"];
  obsDetail: string;
  error: string | null;
  recording: boolean;
}): string | null {
  if (input.error) return input.error;
  if (!input.sessionId) return "No session. File → New session.";
  if (input.backend === "none") return "Desktop has no API.";
  if (input.recording) return null;
  if (input.obs === "down") return "OBS not running.";
  if (input.obs === "degraded") return input.obsDetail || "OBS handshake failed.";
  return null;
}

/** Record controls on the program monitor. Menu Record calls this same row. */
export function Transport({ status }: { status: ApiStatus }) {
  const dispatch = useAppDispatch();
  const [startRec] = useStartRecordingMutation();
  const [stopRec] = useStopRecordingMutation();
  const activeSessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const recordingActive = useAppSelector((s) => s.sessions.recordingActive);
  const recordingStartedAt = useAppSelector((s) => s.sessions.recordingStartedAt);
  const recordingMenuRequest = useAppSelector((s) => s.sessions.recordingMenuRequest);
  const recordingRootDir = useAppSelector((s) => s.sessions.recordingRootDir);
  const transportError = useAppSelector((s) => s.layout.transportError);
  const game = useGameViewStatus();
  const { backend } = getTitan();
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!recordingActive) return;
    const timer = window.setInterval(() => {
      setNow(Date.now());
    }, 500);
    return () => {
      window.clearInterval(timer);
    };
  }, [recordingActive]);

  const openFolder = useCallback(() => {
    if (!recordingRootDir) {
      dispatch(showNotice("Start a recording first, then open its folder from Record."));
      dispatch(setTransportError("No recording folder yet."));
      return;
    }
    void getTitan()
      .openPath(recordingRootDir)
      .then((err) => {
        if (err) {
          dispatch(setTransportError(err));
          dispatch(showNotice(`Could not open folder: ${err}`));
        }
      });
  }, [dispatch, recordingRootDir]);

  const placeMarker = useCallback(() => {
    dispatch(
      logEvent({
        type: "recording.marker",
        category: "recording",
        severity: "notice",
        text: "Marker",
      }),
    );
    dispatch(showNotice("Marker"));
  }, [dispatch]);

  const toggleRecording = useCallback(async () => {
    if (!activeSessionId) {
      dispatch(setTransportError("No session. File → New session."));
      dispatch(showNotice("Create a live session first (File → New session)."));
      return;
    }
    if (backend === "none") {
      dispatch(setTransportError("Desktop has no API."));
      return;
    }
    if (recordingActive) {
      const result = await stopRec(activeSessionId);
      if ("data" in result && result.data) {
        dispatch(setRecordingActive(false));
        dispatch(setTransportError(null));
        dispatch(showNotice("Recording stopped."));
      } else {
        const message = formatApiError(result.error);
        dispatch(setTransportError(message));
        dispatch(showNotice(`Could not stop recording: ${message}`));
      }
      return;
    }
    const result = await startRec(activeSessionId);
    if ("data" in result && result.data) {
      dispatch(setRecordingActive(true));
      dispatch(setRecordingRootDir(result.data.root_dir ?? null));
      dispatch(setTransportError(null));
      dispatch(showNotice("Recording started — OBS StartRecord."));
    } else {
      const message = formatApiError(result.error);
      dispatch(setTransportError(message));
      dispatch(
        showNotice(
          message.includes("OBS not running") ? "OBS not running" : `Could not start recording: ${message}`,
        ),
      );
    }
  }, [activeSessionId, backend, dispatch, recordingActive, startRec, stopRec]);

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

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "m") {
        event.preventDefault();
        placeMarker();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [placeMarker]);

  const note = idleNote({
    sessionId: activeSessionId,
    backend,
    obs: status.obs,
    obsDetail: status.obsDetail,
    error: transportError,
    recording: recordingActive,
  });
  const disabled = !activeSessionId || backend === "none";
  const clock =
    recordingActive && recordingStartedAt != null ? formatRecordingClock(now - recordingStartedAt) : null;

  return (
    <Box
      component="section"
      aria-label="Transport"
      sx={{
        gridArea: "transport",
        display: "flex",
        alignItems: "center",
        flexWrap: "wrap",
        gap: 1,
        px: 1,
        py: 0.75,
        borderRadius: 2,
        bgcolor: "background.paper",
        border: 1,
        borderColor: "divider",
      }}
    >
      <Button
        variant="contained"
        color={recordingActive ? "error" : "primary"}
        disabled={disabled}
        onClick={() => {
          void toggleRecording();
        }}
        aria-label={recordingActive ? "Stop recording" : "Start recording"}
        sx={{ fontWeight: 800, letterSpacing: 1.2, minWidth: 112, minHeight: 40 }}
      >
        {recordingActive ? "STOP" : "REC"}
      </Button>
      <Typography
        variant="body2"
        sx={{ fontFamily: MONO_FONT, fontWeight: 700, minWidth: 72 }}
        aria-label={recordingActive ? "Recording time" : "Recording idle"}
      >
        {clock ?? "00:00:00"}
      </Typography>
      {note ? (
        <Typography variant="body2" color={transportError ? "error" : "text.secondary"} sx={{ minWidth: 0 }}>
          {note}
        </Typography>
      ) : null}
      <Box sx={{ flex: 1 }} />
      <Button size="small" onClick={placeMarker}>
        Marker
      </Button>
      <Button
        size="small"
        disabled={!game?.attached}
        onClick={() => {
          getTitan().gameViewFocus();
        }}
      >
        Focus game
      </Button>
      <Button size="small" startIcon={<FolderOpenIcon />} onClick={openFolder}>
        Folder
      </Button>
    </Box>
  );
}

import VideocamOffOutlinedIcon from "@mui/icons-material/VideocamOffOutlined";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Typography from "@mui/material/Typography";
import { Meter, StatusPill, type Status } from "@titan/ui-kit";

import { useGetActiveRecordingQuery, useGetObsCaptureStatusQuery } from "../../app/api";
import { useAppSelector } from "../../app/hooks";
import { Panel } from "../operations/Panel";

export const TRACKS = [
  { id: "gameplay_video", label: "Gameplay video" },
  { id: "game_audio", label: "Game audio" },
  { id: "mic_audio", label: "Mic audio" },
  { id: "webcam_video", label: "Webcam video" },
] as const;

function trackStatus(state: string | undefined, recordingActive: boolean): { status: Status; label: string } {
  if (!recordingActive) return { status: "off", label: "idle" };
  if (state === "stub") return { status: "degraded", label: "stub" };
  if (state === "recording") return { status: "ok", label: "rec" };
  return { status: "unknown", label: state ?? "idle" };
}

/** Capture panel: OBS probe + per-track stub/OBS state from the active recording manifest. */
export function WebcamPanel() {
  const sessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const recordingActive = useAppSelector((s) => s.sessions.recordingActive);
  const { data: obs } = useGetObsCaptureStatusQuery(undefined, { pollingInterval: 5000 });
  const { data: active } = useGetActiveRecordingQuery(sessionId ?? "", {
    skip: !sessionId,
    pollingInterval: 4000,
  });

  const tracksById = new Map((active?.item?.tracks ?? []).map((t) => [t.id, t] as const));
  const obsConnected = obs?.connected === true || active?.item?.obs?.connected === true;
  const versionRaw = obs?.version?.obsVersion ?? obs?.version?.obs_version;
  const versionLabel =
    typeof versionRaw === "string" || typeof versionRaw === "number" ? String(versionRaw) : "online";
  const subtitle = obsConnected
    ? `OBS ${versionLabel}`
    : obs?.state === "up"
      ? "OBS port up (handshake pending)"
      : "OBS offline — stub tracks on REC";

  return (
    <Panel title="Webcam" subtitle={subtitle} gridArea="webcam">
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 1.4fr) minmax(0, 1fr)",
          gap: 1.5,
          height: "100%",
        }}
      >
        <Box
          aria-label="Webcam preview"
          role="img"
          sx={{
            borderRadius: 2,
            border: 1,
            borderColor: "divider",
            bgcolor: "#0d1119",
            display: "grid",
            placeItems: "center",
            minHeight: 120,
            aspectRatio: "16 / 9",
            alignSelf: "start",
          }}
        >
          <Box sx={{ textAlign: "center", px: 2 }}>
            <VideocamOffOutlinedIcon sx={{ color: "text.disabled", fontSize: 36 }} />
            <Typography variant="caption" display="block" color="text.disabled">
              {obsConnected ? "OBS connected — gameplay preview lands with capture worker" : "Preview off"}
            </Typography>
            <Chip
              size="small"
              sx={{ mt: 1 }}
              label={obsConnected ? "OBS live" : "Stub mode"}
              color={obsConnected ? "success" : "default"}
              variant="outlined"
            />
          </Box>
        </Box>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.25, minWidth: 0 }}>
          <Meter label="Mic level" value={null} min={-60} max={0} unit=" dBFS" />
          <Box
            role="list"
            aria-label="Recording tracks"
            sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}
          >
            {TRACKS.map((track) => {
              const live = tracksById.get(track.id);
              const { status, label } = trackStatus(live?.state, recordingActive);
              const source = live?.source ?? (recordingActive ? "stub" : "idle");
              return (
                <Box role="listitem" key={track.id} sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                  <Typography variant="caption" color="text.secondary" sx={{ flex: 1 }} noWrap>
                    {track.label}
                  </Typography>
                  <StatusPill
                    status={status}
                    label={label}
                    detail={`${track.label}: ${source}${live?.path ? ` → ${live.path}` : ""}`}
                  />
                </Box>
              );
            })}
          </Box>
          <Typography variant="caption" color="text.disabled">
            {recordingActive
              ? obsConnected
                ? "Tracks bound to OBS outputs"
                : "Stub files under session recording/tracks/"
              : "Start REC to allocate track stubs or OBS outputs"}
          </Typography>
        </Box>
      </Box>
    </Panel>
  );
}

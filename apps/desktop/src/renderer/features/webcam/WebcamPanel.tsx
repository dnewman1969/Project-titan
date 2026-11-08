import VideocamOffOutlinedIcon from "@mui/icons-material/VideocamOffOutlined";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { Meter, StatusPill } from "@titan/ui-kit";

import { Panel } from "../operations/Panel";

export const TRACKS = [
  { id: "gameplay_video", label: "Gameplay video" },
  { id: "game_audio", label: "Game audio" },
  { id: "mic_audio", label: "Mic audio" },
  { id: "webcam_video", label: "Webcam video" },
] as const;

/** MJPEG preview, mic meter and per-track recording state arrive in M7.T3 and M8. */
export function WebcamPanel() {
  return (
    <Panel title="Webcam" subtitle="No camera selected" gridArea="webcam">
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
          <Box sx={{ textAlign: "center" }}>
            <VideocamOffOutlinedIcon sx={{ color: "text.disabled", fontSize: 36 }} />
            <Typography variant="caption" display="block" color="text.disabled">
              Preview off
            </Typography>
          </Box>
        </Box>
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.25, minWidth: 0 }}>
          <Meter label="Mic level" value={null} min={-60} max={0} unit=" dBFS" />
          <Box
            role="list"
            aria-label="Recording tracks"
            sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}
          >
            {TRACKS.map((track) => (
              <Box role="listitem" key={track.id} sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <Typography variant="caption" color="text.secondary" sx={{ flex: 1 }} noWrap>
                  {track.label}
                </Typography>
                <StatusPill status="off" label="idle" detail={`${track.label} not recording`} />
              </Box>
            ))}
          </Box>
          <Typography variant="caption" color="text.disabled">
            Dropped frames: n/a
          </Typography>
        </Box>
      </Box>
    </Panel>
  );
}

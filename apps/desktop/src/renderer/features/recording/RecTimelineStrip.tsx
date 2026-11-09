import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { useGetRecordingTimelineQuery } from "../../app/api";
import { useAppSelector } from "../../app/hooks";

function eventLabel(kind: unknown): string {
  if (typeof kind !== "string" || !kind) return "event";
  if (kind === "recording.start") return "REC start";
  if (kind === "recording.stop") return "REC stop";
  if (kind === "play.action") return "Play";
  if (kind === "lesson.proposed") return "Lesson";
  if (kind === "lesson.feedback") return "Outcome";
  if (kind === "agent.commentary") return "Banter";
  return kind;
}

function eventText(ev: Record<string, unknown>): string {
  const text = typeof ev.text === "string" ? ev.text.trim() : "";
  const display = typeof ev.display_name === "string" ? ev.display_name : "";
  if (text && display) return `${display}: ${text}`;
  if (text) return text;
  const actionId = ev.action_id;
  if (typeof actionId === "string") {
    const ok = ev.ok;
    return typeof ok === "boolean" ? `${actionId} (${ok ? "ok" : "fail"})` : actionId;
  }
  const kind = typeof ev.kind === "string" ? ev.kind : "event";
  return kind;
}

/** Live session recording timeline (manifest NDJSON) for Ops Center. */
export function RecTimelineStrip() {
  const sessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const recordingActive = useAppSelector((s) => s.sessions.recordingActive);
  const { data } = useGetRecordingTimelineQuery(
    { sessionId: sessionId ?? "", limit: 40 },
    { skip: !sessionId, pollingInterval: 3000 },
  );

  if (!sessionId) return null;

  const events = data?.events ?? [];
  const newestFirst = [...events].reverse().slice(0, 10);

  return (
    <Box
      aria-label="Session recording timeline"
      sx={{
        px: 1.5,
        py: 1,
        borderBottom: 1,
        borderColor: "divider",
      }}
    >
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.75 }}>
        <Typography variant="caption" color="text.secondary" sx={{ letterSpacing: 0.6 }}>
          REC TIMELINE
        </Typography>
        <Chip
          size="small"
          label={recordingActive ? "Recording" : "Idle"}
          color={recordingActive ? "error" : "default"}
          variant="outlined"
        />
        <Typography variant="caption" color="text.disabled">
          {events.length} event{events.length === 1 ? "" : "s"}
        </Typography>
      </Stack>
      {newestFirst.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {recordingActive
            ? "Waiting for timeline rows (play actions, lessons, commentary)…"
            : "Start REC to write manifest + timeline.ndjson for this session."}
        </Typography>
      ) : (
        <Stack spacing={0.5} sx={{ maxHeight: 110, overflowY: "auto" }}>
          {newestFirst.map((ev, idx) => {
            const kind = Reflect.get(ev, "kind");
            const key = `${String(Reflect.get(ev, "t") ?? idx)}:${String(kind)}:${idx}`;
            return (
              <Stack key={key} direction="row" spacing={1} alignItems="flex-start">
                <Chip size="small" label={eventLabel(kind)} variant="outlined" sx={{ minWidth: 72 }} />
                <Typography variant="body2" sx={{ flex: 1, minWidth: 0 }}>
                  {eventText(ev)}
                </Typography>
              </Stack>
            );
          })}
        </Stack>
      )}
    </Box>
  );
}

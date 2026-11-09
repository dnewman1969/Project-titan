import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { useAppSelector } from "../../app/hooks";
import type { LearnKind } from "./learnSlice";

function kindLabel(kind: LearnKind): string {
  if (kind === "outcome") return "Outcome";
  if (kind === "lesson") return "Lesson";
  return "Discovery";
}

/** Compact live learn-loop feed for the Ops Center agents panel. */
export function LearnFeedbackStrip() {
  const items = useAppSelector((s) => s.learn.items);
  const playEnabled = useAppSelector((s) => s.sessions.playEnabled);
  const sessionId = useAppSelector((s) => s.sessions.activeSessionId);

  if (!sessionId) return null;

  return (
    <Box
      aria-label="Learn loop feedback"
      sx={{
        px: 1.5,
        py: 1,
        borderBottom: 1,
        borderColor: "divider",
        bgcolor: "action.hover",
      }}
    >
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.75 }}>
        <Typography variant="caption" color="text.secondary" sx={{ letterSpacing: 0.6 }}>
          LEARN LOOP
        </Typography>
        <Chip
          size="small"
          label={playEnabled ? "Play on" : "Observe"}
          color={playEnabled ? "success" : "default"}
          variant="outlined"
        />
      </Stack>
      {items.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          {playEnabled
            ? "Waiting for discoveries, play proposals, and action outcomes…"
            : "Enable agent play on a session to record lessons and outcomes here."}
        </Typography>
      ) : (
        <Stack spacing={0.75} sx={{ maxHeight: 120, overflowY: "auto" }}>
          {items.slice(0, 8).map((item) => (
            <Stack key={item.id} direction="row" spacing={1} alignItems="flex-start">
              <Chip
                size="small"
                label={kindLabel(item.kind)}
                color={
                  item.kind === "outcome"
                    ? item.ok === false
                      ? "warning"
                      : "success"
                    : item.kind === "lesson"
                      ? "primary"
                      : "default"
                }
                variant="outlined"
                sx={{ minWidth: 76 }}
              />
              <Typography variant="body2" sx={{ flex: 1, minWidth: 0 }}>
                {item.actionId ? `${item.actionId}: ` : ""}
                {item.text}
              </Typography>
            </Stack>
          ))}
        </Stack>
      )}
    </Box>
  );
}

import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";

import { useGetBlackboardQuery } from "../../app/api";
import { useAppSelector } from "../../app/hooks";
import { ContractBoard } from "./ContractBoard";
import { contractBoardFromEntries } from "./contractBoard";

const EMPTY_WHEN_PLAYING =
  "No contracts yet. Offered contracts, the accepted contract, its goals, and lessons from misses show up here once a career or science flight reports them.";

const EMPTY_WHEN_WATCHING =
  "Play is off. Offered contracts, the accepted contract, its goals, and lessons from misses show up here once a career or science flight reports them.";

/** Career contract board for the Operations Center. Replaces the idle learn-loop placeholder. */
export function LearnFeedbackStrip() {
  const playEnabled = useAppSelector((s) => s.sessions.playEnabled);
  const sessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const { data, isError, isLoading } = useGetBlackboardQuery(
    { sessionId: sessionId ?? "", sinceVersion: undefined },
    { skip: !sessionId, pollingInterval: 2500 },
  );

  if (!sessionId) return null;

  const model = contractBoardFromEntries(data?.entries ?? []);
  let body: ReactNode;
  if (isError && !data) {
    body = (
      <Typography variant="body2" color="text.secondary">
        The contract board could not be read for this session.
      </Typography>
    );
  } else if (isLoading || !data) {
    body = (
      <Typography variant="body2" color="text.secondary">
        Reading the contract board…
      </Typography>
    );
  } else {
    body = (
      <ContractBoard model={model} emptyMessage={playEnabled ? EMPTY_WHEN_PLAYING : EMPTY_WHEN_WATCHING} />
    );
  }

  return (
    <Box
      aria-label="Contracts"
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
          CONTRACTS
        </Typography>
        <Chip
          size="small"
          label={playEnabled ? "Play on" : "Play off"}
          color={playEnabled ? "success" : "default"}
          variant="outlined"
        />
      </Stack>
      <Box sx={{ maxHeight: 240, overflowY: "auto" }}>{body}</Box>
    </Box>
  );
}

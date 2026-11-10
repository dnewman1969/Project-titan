import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";

import { useGetBlackboardQuery } from "../../app/api";
import { useAppSelector } from "../../app/hooks";
import { ContractBoard } from "./ContractBoard";
import { contractBoardFromEntries, contractSessionLine } from "./contractBoard";

const EMPTY_WHEN_PLAYING =
  "No contracts yet. Offered contracts, the accepted contract, its goals, and lessons from misses show up here once a career or science flight reports them.";

const EMPTY_WHEN_WATCHING =
  "Play is off. Offered contracts, the accepted contract, its goals, and lessons from misses show up here once a career or science flight reports them.";

export function useContractSessionLine(): string | null {
  const sessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const { data } = useGetBlackboardQuery(
    { sessionId: sessionId ?? "", sinceVersion: undefined },
    { skip: !sessionId, pollingInterval: 2500 },
  );
  if (!sessionId || !data) return null;
  return contractSessionLine(contractBoardFromEntries(data.entries).accepted);
}

/** Career contract board for the right rail. Stays visible when there is no session. */
export function LearnFeedbackStrip() {
  const playEnabled = useAppSelector((s) => s.sessions.playEnabled);
  const sessionId = useAppSelector((s) => s.sessions.activeSessionId);
  const { data, isError, isLoading } = useGetBlackboardQuery(
    { sessionId: sessionId ?? "", sinceVersion: undefined },
    { skip: !sessionId, pollingInterval: 2500 },
  );

  let body: ReactNode;
  if (!sessionId) {
    body = (
      <Typography variant="body2" color="text.secondary">
        No session. File → New session.
      </Typography>
    );
  } else if (isError && !data) {
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
      <ContractBoard
        model={contractBoardFromEntries(data.entries)}
        emptyMessage={playEnabled ? EMPTY_WHEN_PLAYING : EMPTY_WHEN_WATCHING}
      />
    );
  }

  return (
    <Box
      component="section"
      aria-label="Contracts"
      sx={{
        px: 1.5,
        py: 1,
        minHeight: 0,
      }}
    >
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.75 }}>
        <Typography variant="caption" color="text.secondary" sx={{ letterSpacing: 0.6 }}>
          CONTRACTS
        </Typography>
        {sessionId ? (
          <Chip
            size="small"
            label={playEnabled ? "Play on" : "Play off"}
            color={playEnabled ? "success" : "default"}
            variant="outlined"
          />
        ) : null}
      </Stack>
      {body}
    </Box>
  );
}

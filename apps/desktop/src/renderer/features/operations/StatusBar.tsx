import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import { StatusPill } from "@titan/ui-kit";

import { useAppDispatch, useAppSelector } from "../../app/hooks";
import type { ApiStatus } from "../../app/useApiStatus";
import { TelemetryBar } from "../telemetry/TelemetryBar";
import { useGameViewStatus } from "./GameWindow";
import { togglePanel } from "./layoutSlice";

function attachLabel(attached: boolean | undefined, reason: string | null | undefined): string {
  if (attached) return "attached";
  if (reason) return reason;
  return "not attached";
}

/** Full-width status. Machine numbers are labeled Titan so they are not the RTSS overlay. */
export function StatusBar({ status }: { status: ApiStatus }) {
  const dispatch = useAppDispatch();
  const showTelemetry = useAppSelector((s) => s.layout.panels.telemetry);
  const recordingRootDir = useAppSelector((s) => s.sessions.recordingRootDir);
  const lastEvent = useAppSelector((s) => s.events.entries[0]);
  const game = useGameViewStatus();

  return (
    <Box
      component="section"
      aria-label="Status"
      sx={{
        gridArea: "status",
        display: "flex",
        flexDirection: "column",
        gap: 0.5,
        px: 1,
        py: 0.5,
        borderRadius: 2,
        bgcolor: "background.paper",
        border: 1,
        borderColor: "divider",
        minWidth: 0,
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", minWidth: 0 }}>
        <StatusPill
          status={status.api}
          label="API"
          detail={status.apiDetail}
          pulse={status.api === "unknown"}
        />
        <StatusPill status={status.postgres} label="Database" detail={status.postgresDetail} />
        <StatusPill status={status.services} label="Services" detail={status.servicesDetail} />
        <StatusPill
          status={status.obs}
          label={status.obs === "down" ? "OBS not running" : "OBS"}
          detail={status.obsDetail}
        />
        <StatusPill
          status={game?.attached ? "ok" : "unknown"}
          label="Game"
          detail={attachLabel(game?.attached, game?.reason)}
        />
        <Typography
          variant="caption"
          color="text.secondary"
          noWrap
          sx={{ maxWidth: 220 }}
          title={recordingRootDir ?? ""}
        >
          {recordingRootDir ? recordingRootDir : "No recording folder"}
        </Typography>
        <Box sx={{ flex: 1 }} />
        <Button
          size="small"
          aria-label="Last event"
          onClick={() => {
            dispatch(togglePanel("events"));
          }}
          sx={{ maxWidth: 360, justifyContent: "flex-start" }}
        >
          <Typography variant="caption" noWrap>
            {lastEvent ? lastEvent.text : "No events yet"}
          </Typography>
        </Button>
      </Box>
      {showTelemetry ? <TelemetryBar /> : null}
    </Box>
  );
}

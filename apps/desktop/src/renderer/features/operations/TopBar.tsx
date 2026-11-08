import FiberManualRecordIcon from "@mui/icons-material/FiberManualRecord";
import PowerSettingsNewIcon from "@mui/icons-material/PowerSettingsNew";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { MONO_FONT, StatusPill } from "@titan/ui-kit";

import { useAppDispatch } from "../../app/hooks";
import { getTitan } from "../../app/runtime";
import type { ApiStatus } from "../../app/useApiStatus";
import { triggerKill } from "../../app/useShellBridge";

export function TopBar({ status }: { status: ApiStatus }) {
  const dispatch = useAppDispatch();
  const { killHotkey } = getTitan();
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
      <Chip size="small" variant="outlined" label="No session" sx={{ ml: 1 }} />
      <Box sx={{ flex: 1 }} />
      <StatusPill
        status={status.api}
        label="API"
        detail={status.apiDetail}
        pulse={status.api === "unknown"}
      />
      <StatusPill status={status.postgres} label="Database" detail={status.postgresDetail} />
      <Tooltip title="Recording arrives in M8">
        <Box
          role="status"
          aria-label="Recording: idle"
          sx={{ display: "flex", alignItems: "center", gap: 0.5, px: 1, color: "text.disabled" }}
        >
          <FiberManualRecordIcon sx={{ fontSize: 12 }} />
          <Typography variant="caption" sx={{ fontFamily: MONO_FONT, fontWeight: 700 }}>
            REC --:--:--
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
            triggerKill(dispatch, { source: "button", at: new Date().toISOString() });
          }}
          sx={{ fontWeight: 800, letterSpacing: 1.5, px: 2 }}
        >
          KILL
        </Button>
      </Tooltip>
    </Box>
  );
}

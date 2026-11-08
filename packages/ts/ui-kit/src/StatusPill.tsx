import Box from "@mui/material/Box";
import { alpha } from "@mui/material/styles";
import Typography from "@mui/material/Typography";

import { STATUS_COLORS, type Status } from "./theme";

export interface StatusPillProps {
  status: Status;
  label: string;
  /** Extra detail announced to screen readers and shown as a native tooltip. */
  detail?: string | undefined;
  pulse?: boolean;
}

export function StatusPill({ status, label, detail, pulse = false }: StatusPillProps) {
  const color = STATUS_COLORS[status];
  return (
    <Box
      component="span"
      role="status"
      aria-label={`${label}: ${status}${detail ? ` (${detail})` : ""}`}
      title={detail}
      data-status={status}
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0.75,
        px: 1.25,
        py: 0.25,
        borderRadius: 999,
        border: `1px solid ${alpha(color, 0.45)}`,
        backgroundColor: alpha(color, 0.12),
        whiteSpace: "nowrap",
      }}
    >
      <Box
        component="span"
        aria-hidden
        sx={{
          width: 7,
          height: 7,
          borderRadius: "50%",
          backgroundColor: color,
          boxShadow: `0 0 0 3px ${alpha(color, 0.18)}`,
          ...(pulse && {
            animation: "titan-pulse 1.6s ease-in-out infinite",
            "@keyframes titan-pulse": { "50%": { opacity: 0.35 } },
          }),
        }}
      />
      <Typography component="span" variant="caption" sx={{ fontWeight: 600, color: "text.primary" }}>
        {label}
      </Typography>
    </Box>
  );
}

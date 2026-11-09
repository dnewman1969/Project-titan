import Box from "@mui/material/Box";
import { alpha } from "@mui/material/styles";
import Typography from "@mui/material/Typography";

import { MONO_FONT, STATUS_COLORS } from "./theme";

export interface MeterProps {
  label: string;
  /** Current value, or null when no reading is available (rendered as "n/a"). */
  value: number | null;
  min?: number;
  max: number;
  unit?: string;
  /** Fraction of the range (0..1) at which the bar turns amber and red. */
  warnAt?: number;
  dangerAt?: number;
  format?: (value: number) => string;
  /** Shown in place of a number when `value` is null. */
  emptyLabel?: string;
}

export function meterFraction(value: number, min: number, max: number): number {
  if (max <= min) return 0;
  return Math.min(1, Math.max(0, (value - min) / (max - min)));
}

export function Meter({
  label,
  value,
  min = 0,
  max,
  unit = "",
  warnAt = 0.75,
  dangerAt = 0.9,
  format = (v) => v.toFixed(0),
  emptyLabel = "n/a",
}: MeterProps) {
  const fraction = value === null ? 0 : meterFraction(value, min, max);
  const color =
    value === null
      ? STATUS_COLORS.off
      : fraction >= dangerAt
        ? STATUS_COLORS.down
        : fraction >= warnAt
          ? STATUS_COLORS.degraded
          : STATUS_COLORS.ok;
  const text = value === null ? emptyLabel : `${format(value)}${unit}`;
  return (
    <Box sx={{ minWidth: 0 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 1 }}>
        <Typography variant="overline" color="text.secondary" sx={{ lineHeight: 1.6 }}>
          {label}
        </Typography>
        <Typography variant="caption" sx={{ fontFamily: MONO_FONT, color: "text.primary" }}>
          {text}
        </Typography>
      </Box>
      <Box
        role="meter"
        aria-label={label}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={value ?? undefined}
        aria-valuetext={text}
        sx={{ height: 6, borderRadius: 3, backgroundColor: alpha("#94a3b8", 0.15), overflow: "hidden" }}
      >
        <Box
          sx={{
            height: "100%",
            width: `${(fraction * 100).toFixed(1)}%`,
            backgroundColor: color,
            transition: "width 160ms linear, background-color 160ms linear",
          }}
        />
      </Box>
    </Box>
  );
}

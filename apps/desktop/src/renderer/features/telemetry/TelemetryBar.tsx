import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import type { SystemMetrics } from "@titan/protocol";
import { MONO_FONT } from "@titan/ui-kit";
import { Line, LineChart, YAxis } from "recharts";

import { useAppSelector } from "../../app/hooks";

export interface MetricCell {
  key: string;
  label: string;
  value: string;
}

const NA = "n/a";

function gb(mb: number): string {
  return (mb / 1024).toFixed(1);
}

/** Section 2.13 telemetry bar. Values the backend cannot measure show "n/a" (D18). */
export function formatMetrics(m: SystemMetrics | null): MetricCell[] {
  const gpu = m?.gpu[0];
  const vram =
    gpu?.vram_used_mb != null && gpu.vram_total_mb != null
      ? `${gb(gpu.vram_used_mb)}/${gb(gpu.vram_total_mb)}G`
      : NA;
  return [
    { key: "fps", label: "FPS", value: m?.game_fps != null ? Math.round(m.game_fps).toString() : NA },
    { key: "cpu", label: "CPU", value: m ? `${Math.round(m.cpu_pct)}%` : NA },
    { key: "gpu", label: "GPU", value: gpu?.util_pct != null ? `${Math.round(gpu.util_pct)}%` : NA },
    { key: "vram", label: "VRAM", value: vram },
    { key: "ram", label: "RAM", value: m ? `${gb(m.ram_used_mb)}G` : NA },
    { key: "tokens", label: "Tokens", value: m ? `${(m.tokens_per_min / 1000).toFixed(1)}k/m` : NA },
    { key: "goals", label: "Goals", value: m ? m.goals_active.toString() : NA },
    { key: "tasks", label: "Tasks", value: m ? m.tasks_open.toString() : NA },
  ];
}

export function TelemetryBar() {
  const latest = useAppSelector((s) => s.system.latest);
  const history = useAppSelector((s) => s.system.history);
  const cells = formatMetrics(latest);
  const cpuSeries = history.slice(-120).map((m, i) => ({ i, cpu: m.cpu_pct }));
  return (
    <Paper
      component="section"
      aria-label="Telemetry bar"
      variant="outlined"
      sx={{
        gridArea: "telemetry",
        display: "flex",
        alignItems: "center",
        px: 1,
        py: 0.5,
        gap: 0.5,
        overflowX: "auto",
      }}
    >
      {cells.map((cell, index) => (
        <Box
          key={cell.key}
          sx={{
            display: "flex",
            alignItems: "baseline",
            gap: 0.75,
            px: 1.5,
            borderLeft: index === 0 ? 0 : 1,
            borderColor: "divider",
            whiteSpace: "nowrap",
          }}
        >
          <Typography variant="overline" color="text.secondary" sx={{ lineHeight: 2 }}>
            {cell.label}
          </Typography>
          <Typography
            data-testid={`metric-${cell.key}`}
            variant="body2"
            sx={{
              fontFamily: MONO_FONT,
              fontWeight: 600,
              color: cell.value === NA ? "text.disabled" : "text.primary",
            }}
          >
            {cell.value}
          </Typography>
        </Box>
      ))}
      <Box sx={{ flex: 1 }} />
      {cpuSeries.length > 1 ? (
        <Box aria-label="CPU history" role="img" sx={{ px: 1 }}>
          <LineChart width={120} height={26} data={cpuSeries}>
            <YAxis hide domain={[0, 100]} />
            <Line
              type="monotone"
              dataKey="cpu"
              stroke="#5ec2ff"
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </Box>
      ) : (
        <Typography variant="caption" color="text.disabled" sx={{ px: 1, whiteSpace: "nowrap" }}>
          Live metrics arrive in M1.T6
        </Typography>
      )}
    </Paper>
  );
}

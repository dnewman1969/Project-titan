import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import LinearProgress from "@mui/material/LinearProgress";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import type { ServiceState } from "@titan/protocol";
import { MONO_FONT, StatusPill } from "@titan/ui-kit";

import { useAppDispatch, useAppSelector } from "../../app/hooks";
import { getTitan } from "../../app/runtime";
import { SERVICE_STATUS, splashDismissed } from "../system/supervisorSlice";

const LABELS: Record<string, string> = {
  postgres: "Database (PostgreSQL)",
  redis: "Message bus (Redis)",
  chroma: "Vector index (Chroma)",
  migrate: "Schema migrations",
  api: "Titan API",
};

function describe(service: ServiceState): string {
  if (service.state === "up") return service.detail ?? "healthy";
  return service.detail ?? service.state;
}

/** M1.T5 boot splash: service states while titan-supervisor brings the platform up. */
export function BootSplash() {
  const dispatch = useAppDispatch();
  const { process, detail, status, splashDismissed: dismissed } = useAppSelector((s) => s.supervisor);
  if (getTitan().backend !== "managed" || dismissed || status?.ready) return null;
  const services = status?.services ?? [];
  const headline =
    process === "exited"
      ? "Titan services stopped"
      : process === "restarting"
        ? "Restarting services"
        : "Starting Titan";
  return (
    <Box
      role="dialog"
      aria-label="Starting Titan"
      sx={{
        position: "fixed",
        inset: 0,
        zIndex: 1400,
        display: "grid",
        placeItems: "center",
        bgcolor: "rgba(6, 8, 12, 0.92)",
      }}
    >
      <Paper variant="outlined" sx={{ p: 3, width: 520 }}>
        <Typography variant="h6" component="h2" sx={{ letterSpacing: 2 }}>
          {headline}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {detail ??
            (status ? "Waiting for every service to report healthy." : "Launching titan-supervisor…")}
        </Typography>
        {process !== "exited" && <LinearProgress sx={{ mb: 2 }} />}
        <Box
          component="ul"
          aria-label="Services"
          sx={{ listStyle: "none", m: 0, p: 0, display: "grid", gap: 1 }}
        >
          {services.map((service) => (
            <Box
              component="li"
              key={service.name}
              sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 2 }}
            >
              <Typography variant="body2">{LABELS[service.name] ?? service.name}</Typography>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  noWrap
                  title={describe(service)}
                  sx={{ fontFamily: MONO_FONT, maxWidth: 230 }}
                >
                  {describe(service)}
                </Typography>
                <StatusPill
                  status={SERVICE_STATUS[service.state]}
                  label={service.name}
                  detail={service.state}
                />
              </Box>
            </Box>
          ))}
        </Box>
        <Box sx={{ display: "flex", justifyContent: "flex-end", mt: 2 }}>
          <Button size="small" onClick={() => dispatch(splashDismissed())}>
            Continue without waiting
          </Button>
        </Box>
      </Paper>
    </Box>
  );
}

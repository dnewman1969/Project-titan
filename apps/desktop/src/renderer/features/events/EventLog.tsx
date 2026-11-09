import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import type { GameEvent } from "@titan/protocol";
import { MONO_FONT } from "@titan/ui-kit";
import { useState } from "react";

import { useAppDispatch, useAppSelector } from "../../app/hooks";
import { Panel } from "../operations/Panel";
import { clearLog, type LogEntry } from "./eventsSlice";

type Filter = "all" | GameEvent["category"];

const SEVERITY_COLOR: Record<LogEntry["severity"], string> = {
  debug: "#64748b",
  info: "#5ec2ff",
  notice: "#a98bff",
  warning: "#fbbf24",
  critical: "#f43f5e",
};

const FILTERS: { value: Filter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "game", label: "Game" },
  { value: "agent", label: "Agents" },
  { value: "system", label: "System" },
  { value: "safety", label: "Safety" },
];

function time(iso: string): string {
  const d = new Date(iso);
  return [d.getHours(), d.getMinutes(), d.getSeconds()].map((n) => n.toString().padStart(2, "0")).join(":");
}

/** Event log (Section 2.13). Virtualization and click-to-marker arrive in M7.T4. */
export function EventLog() {
  const dispatch = useAppDispatch();
  const entries = useAppSelector((s) => s.events.entries);
  const [filter, setFilter] = useState<Filter>("all");
  const visible = filter === "all" ? entries : entries.filter((e) => e.category === filter);
  return (
    <Panel
      title="Event Log"
      subtitle={`${entries.length} event${entries.length === 1 ? "" : "s"}`}
      gridArea="events"
      frame="fill"
      flush
      actions={
        <>
          <ToggleButtonGroup
            size="small"
            exclusive
            value={filter}
            onChange={(_e, value: Filter | null) => {
              if (value) setFilter(value);
            }}
            aria-label="Filter events by category"
            sx={{ "& .MuiToggleButton-root": { py: 0, px: 1, fontSize: 11 } }}
          >
            {FILTERS.map((f) => (
              <ToggleButton key={f.value} value={f.value}>
                {f.label}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>
          <Button size="small" onClick={() => dispatch(clearLog())} disabled={entries.length === 0}>
            Clear
          </Button>
        </>
      }
    >
      {visible.length === 0 ? (
        <Box sx={{ height: "100%", display: "grid", placeItems: "center" }}>
          <Typography variant="caption" color="text.disabled">
            No events yet
          </Typography>
        </Box>
      ) : (
        <Box component="ol" aria-label="Events" sx={{ listStyle: "none", m: 0, p: 0 }}>
          {visible.map((entry) => (
            <Box
              component="li"
              key={entry.id}
              data-severity={entry.severity}
              sx={{
                display: "grid",
                gridTemplateColumns: "72px 10px 72px minmax(0, 1fr)",
                alignItems: "center",
                gap: 1,
                px: 1.5,
                py: 0.5,
                borderBottom: 1,
                borderColor: "divider",
                "&:hover": { bgcolor: "action.hover" },
              }}
            >
              <Typography variant="caption" sx={{ fontFamily: MONO_FONT, color: "text.secondary" }}>
                {time(entry.at)}
              </Typography>
              <Box
                aria-label={entry.severity}
                sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: SEVERITY_COLOR[entry.severity] }}
              />
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{ textTransform: "uppercase", fontWeight: 700 }}
              >
                {entry.category}
              </Typography>
              <Typography variant="body2" noWrap title={entry.text}>
                {entry.text}
              </Typography>
            </Box>
          ))}
        </Box>
      )}
    </Panel>
  );
}

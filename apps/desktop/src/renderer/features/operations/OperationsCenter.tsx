import Box from "@mui/material/Box";

import { useAppSelector } from "../../app/hooks";
import type { ApiStatus } from "../../app/useApiStatus";
import { AgentsPanel } from "../agents/AgentsPanel";
import { EventLog } from "../events/EventLog";
import { TelemetryBar } from "../telemetry/TelemetryBar";
import { WebcamPanel } from "../webcam/WebcamPanel";
import { GameWindow } from "./GameWindow";
import type { LayoutState } from "./layoutSlice";
import { TopBar } from "./TopBar";

/** Grid areas and row sizes for the Section 2.13 layout, collapsing hidden panels. */
export function gridTemplate(panels: LayoutState["panels"]): {
  areas: string;
  rows: string;
  columns: string;
} {
  const rows: [string, string][] = [
    ["top top", "auto"],
    ["game game", "minmax(180px, 1fr)"],
  ];
  if (panels.agents || panels.webcam) {
    const left = panels.agents ? "agents" : "webcam";
    const right = panels.webcam ? "webcam" : "agents";
    rows.push([`${left} ${right}`, "minmax(220px, 36%)"]);
  }
  if (panels.telemetry) rows.push(["telemetry telemetry", "auto"]);
  if (panels.events) rows.push(["events events", "minmax(110px, 20%)"]);
  const columns = panels.agents && panels.webcam ? "minmax(0, 1.25fr) minmax(0, 1fr)" : "minmax(0, 1fr) 0px";
  return {
    areas: rows.map(([areas]) => `"${areas}"`).join(" "),
    rows: rows.map(([, size]) => size).join(" "),
    columns,
  };
}

export function OperationsCenter({ status }: { status: ApiStatus }) {
  const panels = useAppSelector((s) => s.layout.panels);
  const template = gridTemplate(panels);
  return (
    <Box
      component="main"
      sx={{
        height: "100vh",
        display: "grid",
        gridTemplateAreas: template.areas,
        gridTemplateRows: template.rows,
        gridTemplateColumns: template.columns,
        gap: 1,
        p: 1,
        bgcolor: "background.default",
        columnGap: panels.agents && panels.webcam ? 1 : 0,
      }}
    >
      <TopBar status={status} />
      <GameWindow />
      {panels.agents && <AgentsPanel />}
      {panels.webcam && <WebcamPanel />}
      {panels.telemetry && <TelemetryBar />}
      {panels.events && <EventLog />}
    </Box>
  );
}

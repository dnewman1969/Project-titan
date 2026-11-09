import Box from "@mui/material/Box";

import { useAppSelector } from "../../app/hooks";
import type { ApiStatus } from "../../app/useApiStatus";
import { AgentsPanel } from "../agents/AgentsPanel";
import { EventLog } from "../events/EventLog";
import { TelemetryBar } from "../telemetry/TelemetryBar";
import { GamesDiscoveryPanel } from "../games/GamesDiscoveryPanel";
import { WebcamPanel } from "../webcam/WebcamPanel";
import { GameWindow } from "./GameWindow";
import type { LayoutState } from "./layoutSlice";
import { TopBar } from "./TopBar";

const AGENT_TRACK = "minmax(240px, 280px)";
const GAME_TRACK = "minmax(0, 1fr)";
const RAIL_TRACK = "minmax(208px, 240px)";

/** Side rail is the thinner column: webcam, telemetry, events, game discovery. */
export function railVisible(panels: LayoutState["panels"]): boolean {
  return panels.webcam || panels.telemetry || panels.events || panels.games;
}

/**
 * Operations Center: a status row, then one tall row whose flexible center is the game.
 * Agents stay in a column. Everything else stacks in a thinner rail so the game is the hero.
 */
export function gridTemplate(panels: LayoutState["panels"]): {
  areas: string;
  rows: string;
  columns: string;
} {
  const rail = railVisible(panels);
  const left = panels.agents ? "agents" : "game";
  const right = rail ? "rail" : "game";
  return {
    areas: `"top top top" "${left} game ${right}"`,
    rows: "auto minmax(0, 1fr)",
    columns: [panels.agents ? AGENT_TRACK : GAME_TRACK, GAME_TRACK, rail ? RAIL_TRACK : GAME_TRACK].join(" "),
  };
}

export function OperationsCenter({ status }: { status: ApiStatus }) {
  const panels = useAppSelector((s) => s.layout.panels);
  const template = gridTemplate(panels);
  const rail = railVisible(panels);
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
        overflow: "hidden",
      }}
    >
      <TopBar status={status} />
      {panels.agents && <AgentsPanel />}
      <GameWindow />
      {rail && (
        <Box
          sx={{
            gridArea: "rail",
            display: "flex",
            flexDirection: "column",
            gap: 1,
            minHeight: 0,
            minWidth: 0,
            overflow: "hidden",
          }}
        >
          {panels.webcam && <WebcamPanel />}
          {panels.telemetry && <TelemetryBar />}
          {panels.games && (
            <Box sx={{ flex: "1 1 120px", minHeight: 120, overflow: "auto" }}>
              <GamesDiscoveryPanel />
            </Box>
          )}
          {panels.events && <EventLog />}
        </Box>
      )}
    </Box>
  );
}

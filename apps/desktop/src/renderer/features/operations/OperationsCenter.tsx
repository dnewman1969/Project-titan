import Box from "@mui/material/Box";
import Dialog from "@mui/material/Dialog";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Drawer from "@mui/material/Drawer";
import { SHELL_MIN_HEIGHT_PX } from "@titan/ui-kit";

import { useAppDispatch, useAppSelector } from "../../app/hooks";
import type { ApiStatus } from "../../app/useApiStatus";
import { AgentsPanel } from "../agents/AgentsPanel";
import { EventLog } from "../events/EventLog";
import { GamesDiscoveryPanel } from "../games/GamesDiscoveryPanel";
import { LearnFeedbackStrip } from "../learn/LearnFeedbackStrip";
import { WebcamPanel } from "../webcam/WebcamPanel";
import { GameWindow } from "./GameWindow";
import type { LayoutState } from "./layoutSlice";
import { setGamesOpen, setPanel } from "./layoutSlice";
import { StatusBar } from "./StatusBar";
import { SessionBar } from "./TopBar";
import { Transport } from "./Transport";

const CREW_TRACK = "280px";
const PROGRAM_TRACK = "minmax(0, 1fr)";
const RAIL_TRACK = "300px";

/**
 * The shell has a pixel min-height. `height: 100%` on `#root` is the viewport, and a hidden
 * window whose first viewport is 0px tall makes that percentage 0. The min-height is what
 * still paints the program frame.
 */
export const operationsFrameSize = {
  height: "100%",
  minHeight: SHELL_MIN_HEIGHT_PX,
  width: "100%",
} as const;

export function railVisible(panels: LayoutState["panels"]): boolean {
  return panels.webcam || panels.contract;
}

/**
 * One program monitor. Crew and the rail can collapse. The session bar, program, and
 * transport cannot. Transport sits on the program column.
 */
export function gridTemplate(panels: LayoutState["panels"]): {
  areas: string;
  rows: string;
  columns: string;
} {
  const crew = panels.crew;
  const rail = railVisible(panels);
  const programLeft = crew ? "crew" : "program";
  const programRight = rail ? "rail" : "program";
  const transportLeft = crew ? "crew" : "transport";
  const transportRight = rail ? "rail" : "transport";
  return {
    areas: `"session session session" "${programLeft} program ${programRight}" "${transportLeft} transport ${transportRight}" "status status status"`,
    rows: "auto minmax(0, 1fr) auto auto",
    columns: [crew ? CREW_TRACK : PROGRAM_TRACK, PROGRAM_TRACK, rail ? RAIL_TRACK : PROGRAM_TRACK].join(" "),
  };
}

export function OperationsCenter({ status }: { status: ApiStatus }) {
  const dispatch = useAppDispatch();
  const panels = useAppSelector((s) => s.layout.panels);
  const gamesOpen = useAppSelector((s) => s.layout.gamesOpen);
  const template = gridTemplate(panels);
  const rail = railVisible(panels);
  return (
    <Box
      component="main"
      sx={{
        ...operationsFrameSize,
        display: "grid",
        gridTemplateAreas: template.areas,
        gridTemplateRows: template.rows,
        gridTemplateColumns: template.columns,
        gap: 1,
        p: 1,
        boxSizing: "border-box",
        bgcolor: "background.default",
        overflow: "hidden",
      }}
    >
      <SessionBar />
      {panels.crew ? <AgentsPanel /> : null}
      <GameWindow />
      <Transport status={status} />
      {rail ? (
        <Box
          component="section"
          aria-label="Rail"
          sx={{
            gridArea: "rail",
            display: "flex",
            flexDirection: "column",
            gap: 1,
            minHeight: 0,
            minWidth: 0,
            overflow: "auto",
          }}
        >
          {panels.webcam ? <WebcamPanel /> : null}
          {panels.contract ? <LearnFeedbackStrip /> : null}
        </Box>
      ) : null}
      <StatusBar status={status} />
      <Drawer
        anchor="bottom"
        open={panels.events}
        onClose={() => {
          dispatch(setPanel({ id: "events", on: false }));
        }}
      >
        <Box sx={{ height: 320, bgcolor: "background.default" }}>
          <EventLog />
        </Box>
      </Drawer>
      <Dialog
        open={gamesOpen}
        onClose={() => {
          dispatch(setGamesOpen(false));
        }}
        aria-labelledby="game-discovery-title"
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle id="game-discovery-title">Game discovery</DialogTitle>
        <DialogContent>
          <GamesDiscoveryPanel />
        </DialogContent>
      </Dialog>
    </Box>
  );
}

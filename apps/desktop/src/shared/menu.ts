/**
 * Menu definition (Section 2.13), shared by the main process (builds the native menu) and the
 * renderer (handles commands and explains which milestone delivers each feature).
 */
export type PanelId = "agents" | "webcam" | "telemetry" | "events";

export interface MenuCommand {
  kind: "command";
  id: string;
  label: string;
  accelerator?: string;
  /** Milestone that implements the command; absent once it works. */
  milestone?: string;
}

export interface MenuToggle {
  kind: "toggle";
  id: `view.toggle.${PanelId}`;
  label: string;
  panel: PanelId;
}

export interface MenuRole {
  kind: "role";
  role: "quit" | "undo" | "redo" | "cut" | "copy" | "paste" | "selectAll";
  label?: string;
}

export interface MenuSeparator {
  kind: "separator";
}

export type MenuEntry = MenuCommand | MenuToggle | MenuRole | MenuSeparator;

export interface MenuSection {
  label: "FILE" | "EDIT" | "VIEW" | "AI" | "RECORD" | "TOOLS" | "HELP";
  items: MenuEntry[];
}

const sep: MenuSeparator = { kind: "separator" };
const cmd = (id: string, label: string, milestone?: string, accelerator?: string): MenuCommand => ({
  kind: "command",
  id,
  label,
  ...(milestone ? { milestone } : {}),
  ...(accelerator ? { accelerator } : {}),
});
const toggle = (panel: PanelId, label: string): MenuToggle => ({
  kind: "toggle",
  id: `view.toggle.${panel}`,
  label,
  panel,
});

export const DOCS_URL =
  "https://github.com/dnewman1969/Project-titan/blob/main/docs/titan-architecture-spec.md";

export const MENU: readonly MenuSection[] = [
  {
    label: "FILE",
    items: [
      cmd("file.newSession", "New Session", "M7.T6", "CmdOrCtrl+N"),
      cmd("file.openSession", "Open Session", "M7.T6", "CmdOrCtrl+O"),
      cmd("file.replaySession", "Replay Session", "M7.T6"),
      sep,
      cmd("file.settings", "Settings", "M2.T3", "CmdOrCtrl+,"),
      sep,
      { kind: "role", role: "quit", label: "Exit" },
    ],
  },
  {
    label: "EDIT",
    items: [
      { kind: "role", role: "undo" },
      { kind: "role", role: "redo" },
      sep,
      { kind: "role", role: "cut" },
      { kind: "role", role: "copy" },
      { kind: "role", role: "paste" },
      { kind: "role", role: "selectAll" },
      sep,
      cmd("edit.personas", "Personas", "M6.T6"),
      cmd("edit.teams", "Teams", "M6.T6"),
      cmd("edit.controlBindings", "Control Bindings", "M4.T4"),
    ],
  },
  {
    label: "VIEW",
    items: [
      toggle("agents", "AI Agents Panel"),
      toggle("webcam", "Webcam Panel"),
      toggle("telemetry", "Telemetry Bar"),
      toggle("events", "Event Log"),
      sep,
      cmd("view.blackboardInspector", "Blackboard Inspector", "M7.T5"),
      cmd("view.messageInspector", "Message Inspector", "M7.T5"),
      cmd("view.telemetryCharts", "Telemetry Charts", "M7.T4"),
    ],
  },
  {
    label: "AI",
    items: [
      cmd("ai.startAgents", "Start Agents", "M6.T6"),
      cmd("ai.stopAgents", "Stop Agents", "M6.T6"),
      sep,
      cmd("ai.models", "Models", "M3.T2"),
      cmd("ai.directorReport", "Director Report", "M7.T5"),
      cmd("ai.memoryBrowser", "Memory Browser", "M9.T4"),
    ],
  },
  {
    label: "RECORD",
    items: [
      cmd("record.start", "Start Recording", "M8.T1"),
      cmd("record.stop", "Stop Recording", "M8.T1"),
      cmd("record.addMarker", "Add Marker", "M8.T3", "CmdOrCtrl+M"),
      sep,
      cmd("record.settings", "Recording Settings", "M8.T1"),
      cmd("record.openFolder", "Open Folder", "M8.T3"),
    ],
  },
  {
    label: "TOOLS",
    items: [
      cmd("tools.gameDiscovery", "Game Discovery", "M4.T5"),
      cmd("tools.integrationInstaller", "Integration Installer", "M4.T5"),
      sep,
      cmd("tools.logs", "Logs", "M10.T4"),
      cmd("tools.diagnostics", "Diagnostics Bundle", "M10.T4"),
    ],
  },
  {
    label: "HELP",
    items: [
      cmd("help.docs", "Documentation"),
      cmd("help.about", "About Titan"),
      cmd("help.licenses", "Licenses", "M10.T4"),
    ],
  },
];

export function findMenuItem(id: string): MenuCommand | MenuToggle | undefined {
  for (const section of MENU) {
    for (const item of section.items) {
      if ((item.kind === "command" || item.kind === "toggle") && item.id === id) return item;
    }
  }
  return undefined;
}

/**
 * Menu definition shared by the main process (native menu) and the renderer (command routing).
 * Every command here has a handler. Items with no product behavior are omitted.
 */
export type PanelId = "crew" | "webcam" | "contract" | "telemetry" | "events";

export interface MenuCommand {
  kind: "command";
  id: string;
  label: string;
  accelerator?: string;
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
  label: "File" | "Edit" | "View" | "AI" | "Record" | "Tools" | "Help";
  items: MenuEntry[];
}

const sep: MenuSeparator = { kind: "separator" };
const cmd = (id: string, label: string, accelerator?: string): MenuCommand => ({
  kind: "command",
  id,
  label,
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

export const BETA_TEST_PLAYBOOK_URL =
  "https://github.com/dnewman1969/Project-titan/blob/main/docs/beta-test-playbook.md";

export const MENU: readonly MenuSection[] = [
  {
    label: "File",
    items: [
      cmd("file.newSession", "New session", "CmdOrCtrl+N"),
      sep,
      { kind: "role", role: "quit", label: "Exit" },
    ],
  },
  {
    label: "Edit",
    items: [
      { kind: "role", role: "undo" },
      { kind: "role", role: "redo" },
      sep,
      { kind: "role", role: "cut" },
      { kind: "role", role: "copy" },
      { kind: "role", role: "paste" },
      { kind: "role", role: "selectAll" },
    ],
  },
  {
    label: "View",
    items: [
      toggle("crew", "Crew"),
      toggle("webcam", "Webcam"),
      toggle("contract", "Contract"),
      toggle("telemetry", "Telemetry"),
      toggle("events", "Event log"),
      cmd("view.gameDiscovery", "Game discovery"),
    ],
  },
  {
    label: "AI",
    items: [cmd("ai.memoryBrowser", "Memory browser")],
  },
  {
    label: "Record",
    items: [
      cmd("record.start", "Start recording"),
      cmd("record.stop", "Stop recording"),
      sep,
      cmd("record.openFolder", "Open recording folder"),
    ],
  },
  {
    label: "Tools",
    items: [
      cmd("tools.gameDiscovery", "Game discovery"),
      cmd("tools.youtubePublish", "YouTube publish"),
      cmd("tools.logs", "Logs"),
      sep,
      cmd("tools.killSwitch", "Kill switch"),
    ],
  },
  {
    label: "Help",
    items: [
      cmd("help.docs", "Documentation"),
      cmd("help.betaTest", "Beta test guide"),
      cmd("help.firstRun", "First-run setup"),
      cmd("help.krpcObs", "kRPC and OBS"),
      cmd("help.about", "About Titan"),
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

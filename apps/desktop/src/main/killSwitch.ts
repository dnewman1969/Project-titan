/**
 * Kill-switch hotkey (Section 6.9 rail 3). Phase 1 has no input path, so a kill only notifies the
 * renderer; M1.T5 also POSTs `/safety/kill`, and Phase 4 adds the titan-actions keyboard hook.
 */
import type { GlobalShortcut } from "electron";

import type { KillSwitchEvent } from "../shared/ipc";

export interface KillSwitchRegistration {
  registered: boolean;
  dispose: () => void;
}

export function registerKillSwitch(
  shortcuts: Pick<GlobalShortcut, "register" | "unregister">,
  accelerator: string,
  onKill: (event: KillSwitchEvent) => void,
  now: () => Date = () => new Date(),
): KillSwitchRegistration {
  const registered = shortcuts.register(accelerator, () => {
    onKill({ source: "hotkey", at: now().toISOString() });
  });
  return {
    registered,
    dispose: () => {
      if (registered) shortcuts.unregister(accelerator);
    },
  };
}

/**
 * Kill-switch hotkey (Section 6.9 rail 3). The hotkey works even when Titan is not focused. Each
 * kill is POSTed to `/safety/kill` (the API persists it and publishes `titan:safety:kill`) and
 * shown in the renderer at once. Phase 1 has no input path, so there is nothing to stop yet;
 * Phase 4 adds the titan-actions named pipe as the second, API-independent path.
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

type FetchFn = (input: string, init?: RequestInit) => Promise<Response>;

/** POST `/api/v1/safety/kill`. Resolves to the HTTP status, or an error message when unreachable. */
export async function postKill(
  apiBase: string,
  token: string,
  source: KillSwitchEvent["source"],
  fetchFn: FetchFn = fetch,
): Promise<number | string> {
  try {
    const response = await fetchFn(`${apiBase}/api/v1/safety/kill`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({ source }),
      signal: AbortSignal.timeout(1000),
    });
    return response.status;
  } catch (err) {
    return err instanceof Error ? err.message : String(err);
  }
}

import { z } from "zod";

import type { PanelId } from "../../shared/menu";

export const SettingsDocumentSchema = z.object({
  version: z.number().int().gte(1),
  values: z.record(z.unknown()),
});
export type SettingsDocument = z.infer<typeof SettingsDocumentSchema>;

const PANEL_IDS: PanelId[] = ["crew", "webcam", "contract", "telemetry", "events"];

function booleanField(record: Record<string, unknown>, key: string): boolean | undefined {
  const value = record[key];
  return typeof value === "boolean" ? value : undefined;
}

/**
 * Parse `ui.layout.panels` booleans. Older settings used `agents` for the crew column
 * and `games` for a grid column. Game discovery is a dialog now, so `games` is ignored.
 */
export function panelsFromSettings(
  values: Record<string, unknown>,
  fallback: Record<PanelId, boolean>,
): Record<PanelId, boolean> {
  const layout = values["ui.layout"];
  if (!layout || typeof layout !== "object") return fallback;
  const panels = (layout as { panels?: unknown }).panels;
  if (!panels || typeof panels !== "object") return fallback;
  const record = panels as Record<string, unknown>;
  const next = { ...fallback };
  for (const id of PANEL_IDS) {
    const value = booleanField(record, id);
    if (value !== undefined) next[id] = value;
  }
  if (booleanField(record, "crew") === undefined) {
    const legacyCrew = booleanField(record, "agents");
    if (legacyCrew !== undefined) next.crew = legacyCrew;
  }
  return next;
}

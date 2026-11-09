import { z } from "zod";

import type { PanelId } from "../../shared/menu";

export const SettingsDocumentSchema = z.object({
  version: z.number().int().gte(1),
  values: z.record(z.unknown()),
});
export type SettingsDocument = z.infer<typeof SettingsDocumentSchema>;

const PANEL_IDS: PanelId[] = ["agents", "webcam", "telemetry", "events", "games"];

const UiLayoutPanelsSchema = z.record(
  z.enum(["agents", "webcam", "telemetry", "events", "games"]),
  z.boolean(),
);

/** Parse `ui.layout.panels` booleans from settings values, falling back to defaults. */
export function panelsFromSettings(
  values: Record<string, unknown>,
  fallback: Record<PanelId, boolean>,
): Record<PanelId, boolean> {
  const layout = values["ui.layout"];
  if (!layout || typeof layout !== "object") return fallback;
  const parsed = UiLayoutPanelsSchema.safeParse((layout as { panels?: unknown }).panels);
  if (!parsed.success) return fallback;
  const next = { ...fallback };
  for (const id of PANEL_IDS) {
    if (typeof parsed.data[id] === "boolean") next[id] = parsed.data[id];
  }
  return next;
}

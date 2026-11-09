/**
 * ComfyUI / static portrait URLs per persona slug.
 *
 * Prefer `VITE_COMFYUI_VIEW_URL` (Comfy `/view` base, e.g. http://127.0.0.1:8188/view).
 * Generated files are expected as `titan-{short-slug}.png` in Comfy output.
 * Fallbacks: `VITE_AGENT_PORTRAIT_BASE/{slug}.png`, then `/portraits/{slug}.png`.
 */

export function portraitSlugKey(personaSlug: string): string {
  const raw = personaSlug.trim().toLowerCase();
  if (!raw) return "agent";
  // Full seed slugs like ksp.director.wernher → wernher; jeb-radio stays intact.
  const dotted = raw.split(".");
  const tail = dotted[dotted.length - 1] ?? raw;
  return tail.replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "") || "agent";
}

export function buildComfyPortraitUrl(viewBase: string, personaSlug: string): string {
  const base = viewBase.replace(/\/$/, "");
  const key = portraitSlugKey(personaSlug);
  const params = new URLSearchParams({
    filename: `titan-${key}.png`,
    type: "output",
  });
  return `${base}?${params.toString()}`;
}

export function buildStaticPortraitUrl(portraitBase: string, personaSlug: string): string {
  const base = portraitBase.replace(/\/$/, "");
  return `${base}/${portraitSlugKey(personaSlug)}.png`;
}

export interface ResolvePortraitOptions {
  personaSlug: string;
  /** Live protocol/sender override when present. */
  overrideUrl?: string | null;
  comfyViewUrl?: string | null;
  portraitBase?: string | null;
}

/** Pure resolver used by UI + unit tests (no import.meta). */
export function resolvePortraitUrl(opts: ResolvePortraitOptions): string {
  const override = opts.overrideUrl?.trim();
  if (override) return override;

  const comfy = opts.comfyViewUrl?.trim();
  if (comfy) return buildComfyPortraitUrl(comfy, opts.personaSlug);

  const custom = opts.portraitBase?.trim();
  if (custom) return buildStaticPortraitUrl(custom, opts.personaSlug);

  return `/portraits/${portraitSlugKey(opts.personaSlug)}.png`;
}

export function comfyViewUrlFromEnv(): string | undefined {
  const raw = import.meta.env.VITE_COMFYUI_VIEW_URL?.trim();
  return raw && raw.length > 0 ? raw.replace(/\/$/, "") : undefined;
}

export function portraitBaseFromEnv(): string | undefined {
  const raw = import.meta.env.VITE_AGENT_PORTRAIT_BASE?.trim();
  return raw && raw.length > 0 ? raw.replace(/\/$/, "") : undefined;
}

export function portraitUrl(personaSlug: string, overrideUrl?: string | null): string {
  return resolvePortraitUrl({
    personaSlug,
    overrideUrl,
    comfyViewUrl: comfyViewUrlFromEnv(),
    portraitBase: portraitBaseFromEnv(),
  });
}

export function usingComfyPortraits(): boolean {
  return Boolean(comfyViewUrlFromEnv());
}

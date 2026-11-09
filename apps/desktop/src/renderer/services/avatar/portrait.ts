/**
 * Optional ComfyUI or static portrait URLs per persona slug.
 * Set `VITE_COMFYUI_VIEW_URL` to the Comfy `view` base (e.g. http://127.0.0.1:8188/view).
 * Drop PNGs in `apps/desktop/public/portraits/{slug}.png` for offline demos.
 */

export function portraitUrl(personaSlug: string): string | undefined {
  const comfyBase = import.meta.env.VITE_COMFYUI_VIEW_URL?.replace(/\/$/, "");
  if (comfyBase) {
    return `${comfyBase}?filename=titan-${personaSlug}.png&type=output`;
  }
  const custom = import.meta.env.VITE_AGENT_PORTRAIT_BASE?.replace(/\/$/, "");
  if (custom) return `${custom}/${personaSlug}.png`;
  return `/portraits/${personaSlug}.png`;
}

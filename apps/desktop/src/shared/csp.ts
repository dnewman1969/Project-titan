/**
 * Renderer Content-Security-Policy (Section 9.6). The build injects it into index.html.
 *
 * `style-src 'unsafe-inline'` is required by MUI/Emotion, which inserts <style> tags at runtime.
 * Dev builds also allow inline scripts and the Vite dev server for React Fast Refresh and HMR.
 */
export interface CspOptions {
  dev: boolean;
  apiPort?: number;
  mediaPort?: number;
  owlTtsPort?: number;
  comfyUiPort?: number;
}

export const DEFAULT_API_PORT = 8765;
export const DEFAULT_MEDIA_PORT = 8767;
/** Owlbox / OpenAI-compatible local TTS (VITE_OWL_TTS_URL). */
export const DEFAULT_OWL_TTS_PORT = 8790;
/** ComfyUI local view host for agent portraits (VITE_COMFYUI_VIEW_URL). */
export const DEFAULT_COMFYUI_PORT = 8188;

export function cspDirectives({
  dev,
  apiPort = DEFAULT_API_PORT,
  mediaPort = DEFAULT_MEDIA_PORT,
  owlTtsPort = DEFAULT_OWL_TTS_PORT,
  comfyUiPort = DEFAULT_COMFYUI_PORT,
}: CspOptions): Record<string, string[]> {
  const api = `127.0.0.1:${apiPort}`;
  const media = `http://127.0.0.1:${mediaPort}`;
  const owlTts = `http://127.0.0.1:${owlTtsPort}`;
  const comfy = `http://127.0.0.1:${comfyUiPort}`;
  return {
    "default-src": ["'self'"],
    "script-src": dev ? ["'self'", "'unsafe-inline'"] : ["'self'"],
    "style-src": ["'self'", "'unsafe-inline'"],
    "connect-src": [
      `http://${api}`,
      `ws://${api}`,
      media,
      owlTts,
      ...(dev ? ["ws://localhost:*", "http://localhost:*"] : []),
    ],
    "img-src": ["'self'", "data:", "blob:", media, comfy],
    "media-src": ["'self'", "blob:", media],
    "object-src": ["'none'"],
    "base-uri": ["'none'"],
    "form-action": ["'none'"],
  };
}

export function buildCsp(options: CspOptions): string {
  return Object.entries(cspDirectives(options))
    .map(([name, sources]) => `${name} ${sources.join(" ")}`)
    .join("; ");
}

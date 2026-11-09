import { extname, join, relative, resolve, sep } from "node:path";

/**
 * The packaged renderer is served from a privileged `app://titan` scheme rather than file://, so it
 * has a real origin for CORS (`api.cors_origins`) and file:// can stay unprivileged (Section 9.6).
 */
export const APP_SCHEME = "app";
export const APP_HOST = "titan";
export const APP_ORIGIN = `${APP_SCHEME}://${APP_HOST}`;
export const APP_INDEX_URL = `${APP_ORIGIN}/index.html`;

function parse(url: string | undefined): URL | null {
  if (!url) return null;
  try {
    return new URL(url);
  } catch {
    return null;
  }
}

/**
 * Whether a URL belongs to the app's own renderer: the Vite dev server origin in development, or
 * app://titan in production. Used to block navigation and to vet IPC senders.
 */
export function isAppUrl(url: string | undefined, devServerUrl: string | undefined): boolean {
  const parsed = parse(url);
  if (!parsed) return false;
  if (devServerUrl) return parsed.origin === new URL(devServerUrl).origin;
  return parsed.protocol === `${APP_SCHEME}:` && parsed.host === APP_HOST;
}

/** Map an app://titan URL to a file inside `root`, or null if it is foreign or escapes the root. */
export function resolveAppFile(root: string, url: string): string | null {
  const parsed = parse(url);
  if (parsed?.protocol !== `${APP_SCHEME}:` || parsed.host !== APP_HOST) return null;
  let pathname: string;
  try {
    pathname = decodeURIComponent(parsed.pathname);
  } catch {
    return null;
  }
  const base = resolve(root);
  const file = resolve(join(base, pathname === "/" ? "index.html" : pathname));
  const rel = relative(base, file);
  if (rel === "" || rel.startsWith("..") || rel.includes(`..${sep}`) || resolve(base, rel) !== file)
    return null;
  return file;
}

/** Content type for a renderer file. A wrong script type makes the module fail and the page stay blank. */
export function mediaType(file: string): string {
  switch (extname(file).toLowerCase()) {
    case ".html":
      return "text/html; charset=utf-8";
    case ".js":
    case ".mjs":
      return "text/javascript; charset=utf-8";
    case ".css":
      return "text/css; charset=utf-8";
    case ".json":
    case ".map":
      return "application/json";
    case ".svg":
      return "image/svg+xml";
    case ".png":
      return "image/png";
    case ".jpg":
    case ".jpeg":
      return "image/jpeg";
    case ".webp":
      return "image/webp";
    case ".ico":
      return "image/x-icon";
    case ".woff2":
      return "font/woff2";
    default:
      return "application/octet-stream";
  }
}

/**
 * Read a renderer file into a response. `net.fetch(file://)` rejects with ERR_FILE_NOT_FOUND on
 * Windows even when the file exists, and a rejected protocol handler leaves the client area blank.
 */
export async function readRendererBody(
  file: string,
  read: (path: string) => Promise<Uint8Array>,
): Promise<Response> {
  try {
    const body = await read(file);
    return new Response(body, { headers: { "content-type": mediaType(file) } });
  } catch {
    return new Response("Not found", {
      status: 404,
      headers: { "content-type": "text/plain; charset=utf-8" },
    });
  }
}

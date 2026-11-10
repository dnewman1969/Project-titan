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

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => {
    if (char === "&") return "&amp;";
    if (char === "<") return "&lt;";
    if (char === ">") return "&gt;";
    if (char === '"') return "&quot;";
    return "&#39;";
  });
}

/**
 * A visible failure, for a bad `app://` read and for the dev server `pnpm dev` loads.
 * Start-Titan uses the dev server, so a file-read fix alone never reaches that window.
 * The page names the error and offers Reload. It is not a solid background color.
 */
export function failurePageHtml(input: { code: string; description: string; reloadUrl: string }): string {
  const code = escapeHtml(input.code);
  const description = escapeHtml(input.description);
  const reload = escapeHtml(input.reloadUrl);
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Titan</title>
    <style>
      html, body { margin: 0; height: 100%; min-height: 760px; background: #0b0e14; color: #e6edf7; font-family: "Segoe UI", system-ui, sans-serif; }
      main { min-height: 760px; box-sizing: border-box; padding: 8px; display: flex; flex-direction: column; }
      header { background: #121722; border: 1px solid #2a3344; border-radius: 8px; padding: 10px 12px; }
      section { flex: 1; margin-top: 8px; min-height: 240px; border: 1px solid #8ea0b8; border-radius: 10px; display: grid; place-items: center; text-align: center; padding: 24px; }
      .label { letter-spacing: 0.12em; font-size: 12px; color: #93a1b8; }
      a { color: #5ec2ff; }
    </style>
  </head>
  <body>
    <main>
      <header>Titan · The Operations Center did not open</header>
      <section>
        <div>
          <p class="label">PROGRAM</p>
          <p>The page failed to load (${code}).</p>
          <p>${description}</p>
          <p><a href="${reload}">Reload</a></p>
        </div>
      </section>
    </main>
  </body>
</html>`;
}

export function failurePageUrl(input: { code: string; description: string; reloadUrl: string }): string {
  return `data:text/html;charset=utf-8,${encodeURIComponent(failurePageHtml(input))}`;
}

export type ClientFailure =
  | {
      kind: "did-fail-load";
      errorCode: number;
      isMainFrame: boolean;
      url: string;
      description: string;
      reloadUrl: string;
    }
  | { kind: "render-process-gone"; description: string; reloadUrl: string };

/** Same failure page for a dev-server load and a packaged `app://` load. */
export function clientFailureReaction(input: ClientFailure): string | null {
  if (input.kind === "did-fail-load") {
    if (!input.isMainFrame || input.errorCode === -3 || input.url.startsWith("data:")) return null;
    return failurePageUrl({
      code: String(input.errorCode),
      description: input.description || "The Operations Center page failed to load.",
      reloadUrl: input.reloadUrl,
    });
  }
  return failurePageUrl({
    code: "renderer-gone",
    description: input.description || "The Operations Center renderer stopped.",
    reloadUrl: input.reloadUrl,
  });
}

/**
 * Read a renderer file into a response. `net.fetch(file://)` rejects with ERR_FILE_NOT_FOUND on
 * Windows even when the file exists, and a rejected protocol handler leaves the client area blank.
 * A missing document is the failure page, not an empty body.
 */
export async function readRendererBody(
  file: string,
  read: (path: string) => Promise<Uint8Array>,
): Promise<Response> {
  try {
    const body = await read(file);
    return new Response(body, { headers: { "content-type": mediaType(file) } });
  } catch {
    if (extname(file).toLowerCase() === ".html") {
      return new Response(
        failurePageHtml({
          code: "ENOENT",
          description: "The Operations Center page could not be read.",
          reloadUrl: APP_INDEX_URL,
        }),
        { status: 404, headers: { "content-type": "text/html; charset=utf-8" } },
      );
    }
    return new Response("Not found", {
      status: 404,
      headers: { "content-type": "text/plain; charset=utf-8" },
    });
  }
}

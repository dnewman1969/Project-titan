import react from "@vitejs/plugin-react";
import { defineConfig } from "electron-vite";
import type { Plugin } from "vite";

import { buildCsp, DEFAULT_API_PORT } from "./src/shared/csp";

const CSP_PLACEHOLDER = "%TITAN_CSP%";

function titanCsp(): Plugin {
  const apiPort = Number(process.env.TITAN__API__PORT) || DEFAULT_API_PORT;
  return {
    name: "titan-csp",
    transformIndexHtml: {
      order: "pre",
      handler(html, ctx) {
        if (!html.includes(CSP_PLACEHOLDER)) throw new Error("index.html is missing the CSP placeholder");
        return html.replace(CSP_PLACEHOLDER, buildCsp({ dev: Boolean(ctx.server), apiPort }));
      },
    },
  };
}

export default defineConfig({
  main: {
    build: { externalizeDeps: true },
  },
  preload: {
    build: { externalizeDeps: true },
  },
  renderer: {
    plugins: [react(), titanCsp()],
  },
});

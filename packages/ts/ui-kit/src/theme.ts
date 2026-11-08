import { alpha, createTheme, type Theme } from "@mui/material/styles";

/** Agent role colours (Section 2.13: chat stream shows a role colour per agent). */
export const ROLE_COLORS = {
  director: "#f5b942",
  flight_engineer: "#ff7a59",
  mission_planner: "#5ec2ff",
  navigator: "#a98bff",
  commentator: "#ff5fa2",
  driver_coach: "#6fdc8c",
  route_planner: "#4fd1c5",
  economy_manager: "#f6e05e",
  maintenance: "#cbd5e0",
  user: "#e2e8f0",
} as const satisfies Record<string, string>;

export type RoleColorKey = keyof typeof ROLE_COLORS;

const FALLBACK_ROLE_COLOR = "#94a3b8";

export function roleColor(role: string): string {
  const base = role.split(".")[0] ?? role;
  return base in ROLE_COLORS ? ROLE_COLORS[base as RoleColorKey] : FALLBACK_ROLE_COLOR;
}

export const STATUS_COLORS = {
  ok: "#34d399",
  degraded: "#fbbf24",
  down: "#f87171",
  unknown: "#94a3b8",
  off: "#64748b",
} as const;

export type Status = keyof typeof STATUS_COLORS;

// No webfonts: the renderer CSP allows no remote origins, so the theme uses the OS UI font stack.
const FONT_STACK =
  '"Segoe UI Variable", "Segoe UI", system-ui, -apple-system, "Helvetica Neue", Arial, sans-serif';
const MONO_STACK = '"Cascadia Mono", "Cascadia Code", Consolas, "SF Mono", Menlo, monospace';

export function createTitanTheme(): Theme {
  const background = { default: "#0b0e14", paper: "#121722" };
  return createTheme({
    palette: {
      mode: "dark",
      primary: { main: "#5ec2ff" },
      secondary: { main: "#a98bff" },
      error: { main: "#f43f5e" },
      warning: { main: "#fbbf24" },
      success: { main: "#34d399" },
      background,
      divider: alpha("#94a3b8", 0.14),
      text: { primary: "#e6edf7", secondary: "#93a1b8" },
    },
    shape: { borderRadius: 10 },
    typography: {
      fontFamily: FONT_STACK,
      fontSize: 13,
      h6: { fontWeight: 650, letterSpacing: 0.2 },
      overline: { fontWeight: 700, letterSpacing: 1.4, fontSize: 11 },
      button: { textTransform: "none", fontWeight: 600 },
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          "html, body, #root": { height: "100%" },
          body: { overflow: "hidden", userSelect: "none" },
          "code, kbd, .mono": { fontFamily: MONO_STACK },
          "*::-webkit-scrollbar": { width: 10, height: 10 },
          "*::-webkit-scrollbar-thumb": {
            backgroundColor: alpha("#94a3b8", 0.25),
            borderRadius: 8,
            border: `2px solid ${background.paper}`,
          },
        },
      },
      MuiPaper: { styleOverrides: { root: { backgroundImage: "none" } } },
      MuiTooltip: { defaultProps: { arrow: true } },
    },
  });
}

export const MONO_FONT = MONO_STACK;

import CssBaseline from "@mui/material/CssBaseline";
import { ThemeProvider } from "@mui/material/styles";
import { SHELL_MIN_HEIGHT_PX, createTitanTheme } from "@titan/ui-kit";
import { Component, StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { Provider } from "react-redux";

import { App } from "./app/App";
import { getTitan } from "./app/runtime";
import { appStore } from "./app/store";

const container = document.getElementById("root");
if (!container) throw new Error("#root missing from index.html");

interface BoundaryState {
  error: string | null;
}

/** Fills the program if React throws, so the window is not the bare background color. */
class ShellErrorBoundary extends Component<{ children: ReactNode }, BoundaryState> {
  override state: BoundaryState = { error: null };

  static getDerivedStateFromError(error: unknown): BoundaryState {
    const message = error instanceof Error ? error.message : "The Operations Center failed to render.";
    return { error: message };
  }

  override render() {
    if (!this.state.error) return this.props.children;
    return (
      <main
        aria-label="Program"
        style={{
          minHeight: SHELL_MIN_HEIGHT_PX,
          height: "100%",
          boxSizing: "border-box",
          padding: 8,
          background: "#0b0e14",
          color: "#e6edf7",
          fontFamily: '"Segoe UI", system-ui, sans-serif',
        }}
      >
        <header
          style={{
            background: "#121722",
            border: "1px solid #2a3344",
            borderRadius: 8,
            padding: "10px 12px",
          }}
        >
          Titan · The Operations Center hit an error
        </header>
        <section
          style={{
            marginTop: 8,
            minHeight: 240,
            border: "1px solid #8ea0b8",
            borderRadius: 10,
            display: "grid",
            placeItems: "center",
            textAlign: "center",
            padding: 24,
          }}
        >
          <div>
            <p style={{ letterSpacing: "0.12em", fontSize: 12, color: "#93a1b8" }}>PROGRAM</p>
            <p>{this.state.error}</p>
          </div>
        </section>
      </main>
    );
  }
}

createRoot(container).render(
  <StrictMode>
    <Provider store={appStore}>
      <ThemeProvider theme={createTitanTheme()}>
        <CssBaseline />
        <ShellErrorBoundary>
          <App />
        </ShellErrorBoundary>
      </ThemeProvider>
    </Provider>
  </StrictMode>,
);

requestAnimationFrame(() => {
  requestAnimationFrame(() => {
    getTitan().rendererCommitted();
  });
});

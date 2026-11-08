import CssBaseline from "@mui/material/CssBaseline";
import { ThemeProvider } from "@mui/material/styles";
import { createTitanTheme } from "@titan/ui-kit";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Provider } from "react-redux";

import { App } from "./app/App";
import { makeStore } from "./app/store";

const container = document.getElementById("root");
if (!container) throw new Error("#root missing from index.html");

createRoot(container).render(
  <StrictMode>
    <Provider store={makeStore()}>
      <ThemeProvider theme={createTitanTheme()}>
        <CssBaseline />
        <App />
      </ThemeProvider>
    </Provider>
  </StrictMode>,
);

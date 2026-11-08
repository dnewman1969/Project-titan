import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";

export interface PanelProps {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  children: ReactNode;
  gridArea: string;
  /** Remove body padding for edge-to-edge content. */
  flush?: boolean;
}

export function Panel({ title, subtitle, actions, children, gridArea, flush = false }: PanelProps) {
  return (
    <Paper
      component="section"
      aria-label={title}
      variant="outlined"
      sx={{
        gridArea,
        minHeight: 0,
        minWidth: 0,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <Box
        component="header"
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1,
          px: 1.5,
          py: 0.75,
          borderBottom: 1,
          borderColor: "divider",
          minHeight: 36,
        }}
      >
        <Typography variant="overline" color="text.secondary">
          {title}
        </Typography>
        {subtitle && (
          <Typography variant="caption" color="text.disabled" noWrap>
            {subtitle}
          </Typography>
        )}
        <Box sx={{ flex: 1 }} />
        {actions}
      </Box>
      <Box sx={{ flex: 1, minHeight: 0, overflow: "auto", p: flush ? 0 : 1.5 }}>{children}</Box>
    </Paper>
  );
}

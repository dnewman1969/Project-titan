import SportsEsportsOutlinedIcon from "@mui/icons-material/SportsEsportsOutlined";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";

/** Placeholder for the desktopCapturer game preview (D11, M7.T1). Display only, never recorded. */
export function GameWindow() {
  return (
    <Paper
      component="section"
      aria-label="Game window"
      variant="outlined"
      sx={{
        gridArea: "game",
        position: "relative",
        minHeight: 0,
        overflow: "hidden",
        display: "grid",
        placeItems: "center",
        background:
          "radial-gradient(1200px 500px at 50% 120%, rgba(94,194,255,0.10), transparent 60%), radial-gradient(800px 400px at 10% -20%, rgba(169,139,255,0.10), transparent 60%), #0d1119",
      }}
    >
      <Box sx={{ position: "absolute", top: 12, left: 12, display: "flex", gap: 1 }}>
        <Chip size="small" label="Scene: none" />
        <Chip size="small" label="Mission: none" />
      </Box>
      <Box sx={{ textAlign: "center", maxWidth: 420, px: 2 }}>
        <SportsEsportsOutlinedIcon sx={{ fontSize: 56, color: "text.disabled" }} />
        <Typography variant="h6" sx={{ mt: 1 }}>
          No game running
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          The live game preview appears here when a session starts. Scene, mission and event toasts overlay
          it.
        </Typography>
      </Box>
    </Paper>
  );
}

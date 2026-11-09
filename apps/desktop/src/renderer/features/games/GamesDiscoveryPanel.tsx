import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { useGetSystemStatusQuery } from "../../app/api";

/** Skeleton for TOOLS → Game Discovery (M4.T5; full installer flows land in M7). */
export function GamesDiscoveryPanel() {
  const { isError } = useGetSystemStatusQuery(undefined);
  return (
    <Paper sx={{ p: 2, height: "100%", overflow: "auto" }} variant="outlined">
      <Stack spacing={1.5}>
        <Typography variant="subtitle1">Game discovery</Typography>
        <Typography variant="body2" color="text.secondary">
          Scan Steam, Epic, GOG, and standalone installs. Integration install and launch use the /games API
          introduced in M4.
        </Typography>
        {isError ? (
          <Alert severity="warning">API unreachable; discovery results stay empty until the API is up.</Alert>
        ) : (
          <Alert severity="info">
            Connect a session to see detected profiles. Scan and install controls ship in M7.
          </Alert>
        )}
        <Button variant="outlined" disabled>
          Scan installed games
        </Button>
      </Stack>
    </Paper>
  );
}

import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { useListGamesQuery, useScanGamesMutation } from "../../app/api";
import { useAppDispatch } from "../../app/hooks";
import { showNotice } from "../operations/layoutSlice";

/** Game discovery: scan installs, then pick a profile when creating a session. */
export function GamesDiscoveryPanel() {
  const dispatch = useAppDispatch();
  const { data, isError, refetch } = useListGamesQuery(undefined);
  const [scan, { isLoading }] = useScanGamesMutation();

  const onScan = async () => {
    const result = await scan(undefined);
    if ("data" in result && result.data) {
      const count = Array.isArray(result.data.detected) ? result.data.detected.length : 0;
      dispatch(showNotice(`Scan complete — ${count} installation(s) detected.`));
      void refetch();
      return;
    }
    dispatch(showNotice("Game scan failed. Is the API up?"));
  };

  return (
    <Paper sx={{ p: 2, height: "100%", overflow: "auto" }} variant="outlined">
      <Stack spacing={1.5}>
        <Typography variant="subtitle1">Game discovery</Typography>
        <Typography variant="body2" color="text.secondary">
          Scan Steam, Epic, GOG, and common install folders. When Kerbal or ETS2 is found, use{" "}
          <strong>File → New session</strong> and pick that slug — adapters attach on session start (fixture
          demo still works with no game installed).
        </Typography>
        {isError ? (
          <Alert severity="warning">API unreachable; discovery needs a live backend.</Alert>
        ) : (
          <Alert severity="info">
            Phase 1 demo does not require a game. Scan when you are ready for real telemetry.
          </Alert>
        )}
        <Button variant="contained" disabled={isLoading || isError} onClick={() => void onScan()}>
          Scan installed games
        </Button>
        <List dense>
          {(data?.items ?? []).map((game) => (
            <ListItem key={game.id}>
              <ListItemText primary={game.name} secondary={`slug: ${game.slug}`} />
            </ListItem>
          ))}
        </List>
      </Stack>
    </Paper>
  );
}

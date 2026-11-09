import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useState } from "react";

import { useCreateGameProfileMutation, useListGamesQuery, useScanGamesMutation } from "../../app/api";
import { useAppDispatch } from "../../app/hooks";
import { showNotice } from "../operations/layoutSlice";

const MANUAL_SLUGS = [
  { slug: "ksp", label: "Kerbal Space Program" },
  { slug: "ets2", label: "Euro Truck Simulator 2" },
  { slug: "ats", label: "American Truck Simulator" },
] as const;

/** Game discovery: scan installs, then pick a profile when creating a session. */
export function GamesDiscoveryPanel() {
  const dispatch = useAppDispatch();
  const { data, isError, refetch } = useListGamesQuery(undefined);
  const [scan, { isLoading: scanning }] = useScanGamesMutation();
  const [createProfile, { isLoading: registering }] = useCreateGameProfileMutation();
  const [lastDetected, setLastDetected] = useState<
    Array<{ game_slug: string; install_path: string; profile_id: string }>
  >([]);
  const [manualSlug, setManualSlug] = useState<string>("ksp");
  const [manualExe, setManualExe] = useState("");
  const [extraPath, setExtraPath] = useState("");

  const profileCount = (data?.items ?? []).reduce((n, g) => n + (g.profiles?.length ?? 0), 0);

  const onScan = async () => {
    const extra = extraPath.trim() ? [extraPath.trim()] : [];
    const result = await scan({ extra_paths: extra });
    if ("data" in result && result.data) {
      const detected = Array.isArray(result.data.detected) ? result.data.detected : [];
      setLastDetected(detected);
      dispatch(showNotice(`Scan complete: ${detected.length} Titan game install(s) found.`));
      void refetch();
      return;
    }
    dispatch(showNotice("Game scan failed. Is the API up?"));
  };

  const onRegisterPath = async () => {
    const exe = manualExe.trim();
    if (!exe) {
      dispatch(showNotice("Paste the full path to the game .exe first."));
      return;
    }
    const result = await createProfile({ game_slug: manualSlug, executable_path: exe });
    if ("data" in result && result.data) {
      dispatch(showNotice(`Registered ${manualSlug} install: ${result.data.install_path}`));
      setManualExe("");
      void refetch();
      return;
    }
    dispatch(showNotice("Could not register install. Check the .exe path and API logs."));
  };

  return (
    <Paper sx={{ p: 2, height: "100%", overflow: "auto" }} variant="outlined">
      <Stack spacing={1.5}>
        <Typography variant="subtitle1">Game discovery</Typography>
        <Typography variant="body2" color="text.secondary">
          Scans Steam (registry + libraryfolders), Epic manifests, GOG Galaxy folders, and optional paths.
          Supported slugs: KSP, ETS2, ATS. Then use <strong>File - New session</strong>, pick an installation,
          enable <strong>agent play</strong>, and start.
        </Typography>
        {isError ? (
          <Alert severity="warning">API unreachable; discovery needs a live backend.</Alert>
        ) : profileCount === 0 ? (
          <Alert severity="info">
            No installs in the database yet. Run Scan, or register a path to the game .exe below (for example
            KSP_x64.exe under steamapps\common).
          </Alert>
        ) : (
          <Alert severity="success">{profileCount} install profile(s) ready for New session.</Alert>
        )}
        <TextField
          label="Extra scan folder (optional)"
          placeholder="C:\Program Files (x86)\Steam\steamapps\common"
          value={extraPath}
          onChange={(e) => {
            setExtraPath(e.target.value);
          }}
          fullWidth
          size="small"
        />
        <Button variant="contained" disabled={scanning || isError} onClick={() => void onScan()}>
          Scan installed games
        </Button>
        {lastDetected.length > 0 ? (
          <List dense>
            {lastDetected.map((hit) => (
              <ListItem key={hit.profile_id}>
                <ListItemText primary={`${hit.game_slug}`} secondary={hit.install_path} />
              </ListItem>
            ))}
          </List>
        ) : null}
        <Typography variant="subtitle2">Manual install path</Typography>
        <TextField
          select
          label="Game"
          value={manualSlug}
          onChange={(e) => {
            setManualSlug(e.target.value);
          }}
          fullWidth
          size="small"
        >
          {MANUAL_SLUGS.map((g) => (
            <MenuItem key={g.slug} value={g.slug}>
              {g.label}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          label="Path to game .exe"
          placeholder="C:\...\Kerbal Space Program\KSP_x64.exe"
          value={manualExe}
          onChange={(e) => {
            setManualExe(e.target.value);
          }}
          fullWidth
          size="small"
        />
        <Button variant="outlined" disabled={registering || isError} onClick={() => void onRegisterPath()}>
          Register install path
        </Button>
        <List dense>
          {(data?.items ?? []).map((game) => (
            <ListItem key={game.id}>
              <ListItemText
                primary={game.name}
                secondary={`${game.slug}${
                  game.profiles?.length ? ` - ${game.profiles.length} install(s)` : " - none"
                }`}
              />
            </ListItem>
          ))}
        </List>
      </Stack>
    </Paper>
  );
}

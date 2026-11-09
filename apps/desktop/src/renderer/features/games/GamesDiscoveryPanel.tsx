import Alert from "@mui/material/Alert";
import FolderOpenIcon from "@mui/icons-material/FolderOpen";
import Button from "@mui/material/Button";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemText from "@mui/material/ListItemText";
import MenuItem from "@mui/material/MenuItem";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useEffect, useState } from "react";

import { useCreateGameProfileMutation, useListGamesQuery, useScanGamesMutation } from "../../app/api";
import { formatApiError } from "../../app/formatApiError";
import { useAppDispatch } from "../../app/hooks";
import { getTitan } from "../../app/runtime";
import { logEvent } from "../events/eventsSlice";
import { showNotice } from "../operations/layoutSlice";

const MANUAL_SLUGS = [
  { slug: "ksp", label: "Kerbal Space Program" },
  { slug: "ets2", label: "Euro Truck Simulator 2" },
  { slug: "ats", label: "American Truck Simulator" },
] as const;

/** Game discovery: scan installs, then pick a profile when creating a session. */
export function GamesDiscoveryPanel() {
  const dispatch = useAppDispatch();
  const { data, error: listError, isError, refetch } = useListGamesQuery(undefined);
  const [scan, { isLoading: scanning }] = useScanGamesMutation();
  const [createProfile, { isLoading: registering }] = useCreateGameProfileMutation();
  const [lastDetected, setLastDetected] = useState<
    Array<{ game_slug: string; install_path: string; profile_id: string }>
  >([]);
  const [manualSlug, setManualSlug] = useState<string>("ksp");
  const [manualExe, setManualExe] = useState("");
  const [extraPath, setExtraPath] = useState("");
  const [panelError, setPanelError] = useState<string | null>(null);

  const profileCount = (data?.items ?? []).reduce((n, g) => n + (g.profiles?.length ?? 0), 0);

  useEffect(() => {
    void refetch();
  }, [refetch]);

  const onScan = async () => {
    setPanelError(null);
    const extra = extraPath.trim() ? [extraPath.trim()] : [];
    const result = await scan({ extra_paths: extra });
    if ("data" in result && result.data) {
      const detected = Array.isArray(result.data.detected) ? result.data.detected : [];
      setLastDetected(detected);
      const ctx = result.data.scan_context;
      const steamRoots = ctx?.steam_libraries?.length ?? 0;
      const notice =
        detected.length > 0
          ? `Scan complete: ${detected.length} Titan game install(s) found.`
          : `Scan complete: 0 Titan installs (checked ${steamRoots} Steam library root(s)). Use Register below with Browse….`;
      dispatch(showNotice(notice));
      void refetch();
      return;
    }
    const msg = formatApiError(result.error);
    setPanelError(`Game scan failed: ${msg}`);
    dispatch(showNotice(`Game scan failed: ${msg}`));
    dispatch(logEvent({ type: "games.scan_failed", category: "system", severity: "critical", text: msg }));
  };

  const onBrowseExecutable = async () => {
    const picked = await getTitan().pickExecutable();
    if (picked) {
      setManualExe(picked);
    }
  };

  const onRegisterPath = async () => {
    setPanelError(null);
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
    const msg = formatApiError(result.error);
    setPanelError(`Register install failed: ${msg}`);
    dispatch(showNotice(`Register install failed: ${msg}`));
    dispatch(
      logEvent({ type: "games.register_failed", category: "system", severity: "critical", text: msg }),
    );
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
        {panelError ? (
          <Alert
            severity="error"
            onClose={() => {
              setPanelError(null);
            }}
          >
            {panelError}
          </Alert>
        ) : null}
        {isError ? (
          <Alert severity="error">
            Could not reach the games API: {formatApiError(listError)}. Start the supervisor API, then retry Scan
            or Register.
          </Alert>
        ) : profileCount === 0 ? (
          <Alert severity="warning" variant="outlined">
            Scan did not find installs? Use <strong>Register install path</strong> below with the full path to
            your game .exe (for example <code>KSP_x64.exe</code>). Then open File → New session and pick that
            installation — registered paths work even when Scan returns zero.
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
                <ListItemText primary={hit.game_slug} secondary={hit.install_path} />
              </ListItem>
            ))}
          </List>
        ) : null}
        <Paper variant="outlined" sx={{ p: 1.5, bgcolor: "action.hover" }}>
          <Typography variant="subtitle2" gutterBottom>
            Register install path (recommended when Scan finds nothing)
          </Typography>
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
          <Stack direction="row" spacing={1} alignItems="flex-start">
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
            <Button
              variant="outlined"
              size="small"
              disabled={isError}
              startIcon={<FolderOpenIcon />}
              onClick={() => void onBrowseExecutable()}
              sx={{ mt: 0.5, whiteSpace: "nowrap" }}
            >
              Browse…
            </Button>
          </Stack>
          <Button
            variant="contained"
            color="secondary"
            disabled={registering || isError || manualExe.trim().length === 0}
            onClick={() => void onRegisterPath()}
          >
            Register install path
          </Button>
        </Paper>
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

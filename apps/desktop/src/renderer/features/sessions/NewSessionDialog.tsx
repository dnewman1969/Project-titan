import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import FormHelperText from "@mui/material/FormHelperText";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useEffect, useState } from "react";

import { useCreateSessionMutation, useListGamesQuery, useStartSessionMutation } from "../../app/api";
import { formatApiError } from "../../app/formatApiError";
import { useAppDispatch, useAppSelector } from "../../app/hooks";
import { logEvent } from "../events/eventsSlice";
import { showNotice, showPanel } from "../operations/layoutSlice";
import { closeSessionDialog, setActiveSession } from "./sessionsSlice";

const FALLBACK_GAMES = [
  { slug: "ksp", label: "Kerbal Space Program" },
  { slug: "ets2", label: "Euro Truck Simulator 2" },
  { slug: "ats", label: "American Truck Simulator" },
] as const;

function rtkMutationStatus(error: unknown): number | null {
  if (typeof error !== "object" || error === null || !("status" in error)) return null;
  const status = Reflect.get(error, "status");
  return typeof status === "number" ? status : null;
}

function defaultTitle(play: boolean, gameLabel: string): string {
  return play ? `Learn and play - ${gameLabel}` : `Observe - ${gameLabel}`;
}

/** Create a live session against a scanned install (or fixture fallback when none selected). */
export function NewSessionDialog() {
  const open = useAppSelector((s) => s.sessions.dialog === "new");
  const dispatch = useAppDispatch();
  const [title, setTitle] = useState("Learn and play - Kerbal Space Program");
  const [titleTouched, setTitleTouched] = useState(false);
  const [gameSlug, setGameSlug] = useState<string>("ksp");
  const [profileId, setProfileId] = useState<string>("");
  const [launchGame, setLaunchGame] = useState(false);
  const [agentPlay, setAgentPlay] = useState(true);
  const [recordOnStart, setRecordOnStart] = useState(true);
  const { data: gamesList, refetch: refetchGames } = useListGamesQuery(undefined, {
    refetchOnMountOrArgChange: true,
  });
  useEffect(() => {
    if (open) {
      void refetchGames();
    }
  }, [open, refetchGames]);
  const [createSession, { isLoading: creating }] = useCreateSessionMutation();
  const [startSession, { isLoading: starting }] = useStartSessionMutation();

  const games: Array<{ slug: string; label: string; profiles?: Array<{ id: string; label: string }> }> =
    gamesList?.items.map((g) => ({
      slug: g.slug,
      label: g.name,
      profiles: (g.profiles ?? []).map((p) => ({
        id: p.id,
        label: p.install_path,
      })),
    })) ?? [...FALLBACK_GAMES];
  const game = games.find((g) => g.slug === gameSlug) ?? games[0];
  const profiles = game?.profiles ?? [];
  const effectiveProfileId = profiles.some((p) => p.id === profileId) ? profileId : (profiles[0]?.id ?? "");
  const sessionSource: "live" | "fixture" = effectiveProfileId ? "live" : "fixture";

  const isLoading = creating || starting;
  const onClose = () => {
    dispatch(closeSessionDialog());
  };

  const syncTitle = (play: boolean, slug: string) => {
    if (titleTouched) return;
    const label = games.find((g) => g.slug === slug)?.label ?? slug;
    setTitle(defaultTitle(play, label));
  };

  const onOpenGameDiscovery = () => {
    dispatch(showPanel("games"));
    dispatch(closeSessionDialog());
    dispatch(
      showNotice(
        "Game discovery: Scan, or Browse… for KSP_x64.exe, then Register install path. Reopen File → New session.",
      ),
    );
  };

  const onCreate = async () => {
    if (!game) return;
    if (typeof localStorage !== "undefined") {
      localStorage.setItem("titan.skipAutoDemo", "1");
    }
    const sessionTitle = title.trim() || defaultTitle(agentPlay, game.label);
    const result = await createSession({
      game_slug: game.slug,
      game_profile_id: effectiveProfileId || undefined,
      title: sessionTitle,
      mode: agentPlay ? "autonomous" : "observe",
      settings: {
        agents_enabled: true,
        ...(agentPlay ? { play_enabled: true } : {}),
        ...(recordOnStart ? { record_on_start: true } : {}),
        demo_telemetry: sessionSource === "fixture",
        session_source: sessionSource,
      },
    });
    if ("data" in result && result.data) {
      const started = await startSession({
        sessionId: result.data.id,
        launch_game: launchGame && Boolean(effectiveProfileId),
      });
      if ("data" in started && started.data) {
        const dataDir = Reflect.get(started.data, "data_dir");
        const recordingRoot =
          recordOnStart && typeof dataDir === "string" && dataDir.length > 0 ? `${dataDir}/recording` : null;
        const liveTitle = started.data.title?.trim() || sessionTitle;
        dispatch(
          setActiveSession({
            id: started.data.id,
            title: liveTitle,
            recordingActive: recordOnStart,
            recordingRootDir: recordingRoot,
            sessionSource,
            playEnabled: agentPlay,
          }),
        );
        const kind =
          sessionSource === "fixture"
            ? "Fixture session"
            : agentPlay
              ? "Learn-and-play session"
              : "Live observe session";
        dispatch(showNotice(`${kind}: ${liveTitle}`));
        dispatch(closeSessionDialog());
        return;
      }
      const startMsg = formatApiError(started.error);
      dispatch(showNotice(`Session start failed: ${startMsg}`));
      dispatch(
        logEvent({
          type: "session.start_failed",
          category: "system",
          severity: "critical",
          text: startMsg,
        }),
      );
      return;
    }
    const status = rtkMutationStatus(result.error);
    if (status === 404 || status === 405 || status === 501) {
      dispatch(
        showNotice(
          "Session API is not on this backend yet. Full new/start/stop flows land with M6 session controller.",
        ),
      );
      dispatch(closeSessionDialog());
      return;
    }
    const createMsg = formatApiError(result.error);
    dispatch(showNotice(`Could not create session: ${createMsg}`));
    dispatch(
      logEvent({
        type: "session.create_failed",
        category: "system",
        severity: "critical",
        text: createMsg,
      }),
    );
  };

  return (
    <Dialog open={open} onClose={onClose} aria-labelledby="new-session-title" maxWidth="sm" fullWidth>
      <DialogTitle id="new-session-title">New session</DialogTitle>
      <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
        <Typography variant="body2" color="text.secondary">
          Agents watch telemetry, write lessons, and (when play is on) propose controls that{" "}
          <code>titan-actions</code> executes via kRPC, SCS, or HIL.
        </Typography>
        <Alert severity={sessionSource === "live" ? "success" : "info"} sx={{ width: "100%" }}>
          {sessionSource === "live"
            ? "Live install attached - telemetry and play target this profile."
            : "No install attached - fixture/demo telemetry only (software HIL path for play)."}
        </Alert>
        <TextField
          label="Title"
          value={title}
          onChange={(e) => {
            setTitleTouched(true);
            setTitle(e.target.value);
          }}
          fullWidth
          autoFocus
        />
        <TextField
          select
          label="Game"
          value={gameSlug}
          onChange={(e) => {
            const slug = e.target.value;
            setGameSlug(slug);
            const picked = games.find((g) => g.slug === slug);
            setProfileId(picked?.profiles?.[0]?.id ?? "");
            setLaunchGame(false);
            syncTitle(agentPlay, slug);
          }}
          fullWidth
        >
          {games.map((g) => (
            <MenuItem key={g.slug} value={g.slug}>
              {g.label}
              {(g.profiles?.length ?? 0) > 0 ? ` (${g.profiles?.length} install(s))` : ""}
            </MenuItem>
          ))}
        </TextField>
        {profiles.length > 0 ? (
          <TextField
            select
            label="Installation"
            value={effectiveProfileId}
            onChange={(e) => {
              setProfileId(e.target.value);
            }}
            fullWidth
            helperText="Registered paths work even when Scan finds nothing."
          >
            {profiles.map((p) => (
              <MenuItem key={p.id} value={p.id}>
                {p.label}
              </MenuItem>
            ))}
          </TextField>
        ) : (
          <Alert
            severity="warning"
            variant="outlined"
            sx={{ width: "100%" }}
            action={
              <Button color="inherit" size="small" onClick={onOpenGameDiscovery}>
                Open Game discovery
              </Button>
            }
          >
            No install for <strong>{game?.label ?? gameSlug}</strong>. View → Games → Browse… for{" "}
            <code>KSP_x64.exe</code> (or Scan), Register install path, then reopen New session. Without a
            profile, Launch and live play stay off (fixture/demo telemetry only).
          </Alert>
        )}
        <FormControlLabel
          control={
            <Checkbox
              checked={agentPlay}
              onChange={(e) => {
                const next = e.target.checked;
                setAgentPlay(next);
                syncTitle(next, gameSlug);
              }}
            />
          }
          label="Enable agent play (learn-and-play beta)"
        />
        {agentPlay ? (
          <FormHelperText sx={{ mt: -1.5, mx: 0 }}>
            {sessionSource === "live"
              ? "Starts the actions worker against the selected install (kRPC/SCS when available)."
              : "Starts the actions worker with TITAN_PLAY_BACKEND=hil for software play without a game."}
          </FormHelperText>
        ) : null}
        <FormControlLabel
          control={
            <Checkbox
              checked={recordOnStart}
              onChange={(e) => {
                setRecordOnStart(e.target.checked);
              }}
            />
          }
          label="Record session (manifest + timeline; OBS optional)"
        />
        <FormControlLabel
          control={
            <Checkbox
              checked={launchGame}
              disabled={!effectiveProfileId}
              onChange={(e) => {
                setLaunchGame(e.target.checked);
              }}
            />
          }
          label="Launch game executable when session starts"
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" disabled={isLoading} onClick={() => void onCreate()}>
          {agentPlay ? "Start learn and play" : "Create"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

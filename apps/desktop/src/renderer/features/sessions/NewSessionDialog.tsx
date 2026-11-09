import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import { useState } from "react";

import { useCreateSessionMutation, useListGamesQuery, useStartSessionMutation } from "../../app/api";
import { useAppDispatch, useAppSelector } from "../../app/hooks";
import { showNotice } from "../operations/layoutSlice";
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

/** Create a live session against a scanned install (or fixture fallback when none selected). */
export function NewSessionDialog() {
  const open = useAppSelector((s) => s.sessions.dialog === "new");
  const dispatch = useAppDispatch();
  const [title, setTitle] = useState("Observe session");
  const [gameSlug, setGameSlug] = useState<string>("ksp");
  const [profileId, setProfileId] = useState<string>("");
  const [launchGame, setLaunchGame] = useState(false);
  const [agentPlay, setAgentPlay] = useState(false);
  const [recordOnStart, setRecordOnStart] = useState(true);
  const { data: gamesList } = useListGamesQuery(undefined);
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

  const isLoading = creating || starting;
  const onClose = () => {
    dispatch(closeSessionDialog());
  };

  const onCreate = async () => {
    if (!game) return;
    const sessionTitle = title.trim() || "Observe session";
    const result = await createSession({
      game_slug: game.slug,
      game_profile_id: effectiveProfileId || undefined,
      title: sessionTitle,
      mode: "observe",
      settings: {
        agents_enabled: true,
        ...(agentPlay ? { play_enabled: true } : {}),
        ...(recordOnStart ? { record_on_start: true } : {}),
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
        dispatch(
          setActiveSession({
            id: started.data.id,
            title: started.data.title,
            recordingActive: recordOnStart,
            recordingRootDir: recordingRoot,
          }),
        );
        dispatch(showNotice(`Live session: ${started.data.title}`));
        dispatch(closeSessionDialog());
        return;
      }
      dispatch(showNotice(`Session created but could not start: check API logs.`));
      dispatch(closeSessionDialog());
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
    dispatch(showNotice("Could not create a session. Check the API logs and try again."));
  };

  return (
    <Dialog open={open} onClose={onClose} aria-labelledby="new-session-title" maxWidth="sm" fullWidth>
      <DialogTitle id="new-session-title">New session</DialogTitle>
      <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, pt: 1 }}>
        <TextField
          label="Title"
          value={title}
          onChange={(e) => {
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
          }}
          fullWidth
        >
          {games.map((g) => (
            <MenuItem key={g.slug} value={g.slug}>
              {g.label}
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
            helperText="Use Scan installed games first if your copy is missing."
          >
            {profiles.map((p) => (
              <MenuItem key={p.id} value={p.id}>
                {p.label}
              </MenuItem>
            ))}
          </TextField>
        ) : (
          <FormControlLabel
            control={<Checkbox disabled checked={false} />}
            label="No install detected — session will use fixture/demo telemetry until you scan."
          />
        )}
        <FormControlLabel
          control={
            <Checkbox
              checked={agentPlay}
              onChange={(e) => {
                setAgentPlay(e.target.checked);
              }}
            />
          }
          label="Enable agent play (beta)"
        />
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
          Create
        </Button>
      </DialogActions>
    </Dialog>
  );
}

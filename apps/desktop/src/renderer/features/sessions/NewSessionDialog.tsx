import FolderOpenIcon from "@mui/icons-material/FolderOpen";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
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

import {
  useCreateGameProfileMutation,
  useCreateSessionMutation,
  useGetPlayReadinessQuery,
  useListGamesQuery,
  useStartSessionMutation,
} from "../../app/api";
import { formatApiError } from "../../app/formatApiError";
import { useAppDispatch, useAppSelector } from "../../app/hooks";
import { getTitan } from "../../app/runtime";
import { logEvent } from "../events/eventsSlice";
import { showNotice, showPanel } from "../operations/layoutSlice";
import { closeSessionDialog, setActiveSession, type PlayBackendKind } from "./sessionsSlice";

const FALLBACK_GAMES = [
  { slug: "ksp", label: "Kerbal Space Program" },
  { slug: "ets2", label: "Euro Truck Simulator 2" },
  { slug: "ats", label: "American Truck Simulator" },
] as const;

const GAME_EXE_HINT: Record<string, string> = {
  ksp: "KSP_x64.exe",
  ets2: "eurotrucks2.exe",
  ats: "amtrucks.exe",
};

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
  const [dialogError, setDialogError] = useState<string | null>(null);
  const {
    data: gamesList,
    error: gamesListError,
    isError: gamesListFailed,
    refetch: refetchGames,
  } = useListGamesQuery(undefined, {
    refetchOnMountOrArgChange: true,
  });
  useEffect(() => {
    if (open) {
      void refetchGames();
    }
  }, [open, refetchGames]);
  const [createSession, { isLoading: creating }] = useCreateSessionMutation();
  const [startSession, { isLoading: starting }] = useStartSessionMutation();
  const [createProfile, { isLoading: registering }] = useCreateGameProfileMutation();

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
  const {
    data: readiness,
    error: readinessError,
    isError: readinessFailed,
  } = useGetPlayReadinessQuery(
    { gameSlug: gameSlug, source: sessionSource },
    { skip: !open || !agentPlay, refetchOnMountOrArgChange: true },
  );
  const playAttach = readiness?.play_attach;
  const exeHint = GAME_EXE_HINT[gameSlug] ?? "game .exe";

  const isLoading = creating || starting || registering;
  const onClose = () => {
    setDialogError(null);
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

  const onBrowseAndRegister = async () => {
    setDialogError(null);
    const picked = await getTitan().pickExecutable();
    if (!picked?.trim()) {
      return;
    }
    const result = await createProfile({ game_slug: gameSlug, executable_path: picked.trim() });
    if ("data" in result && result.data) {
      setProfileId(result.data.id);
      dispatch(showNotice(`Registered ${game?.label ?? gameSlug}: ${result.data.install_path}`));
      await refetchGames();
      return;
    }
    const msg = formatApiError(result.error);
    setDialogError(`Register install failed: ${msg}`);
    dispatch(
      logEvent({
        type: "games.register_failed",
        category: "system",
        severity: "critical",
        text: msg,
      }),
    );
  };

  const onCreate = async () => {
    if (!game) return;
    if (typeof localStorage !== "undefined") {
      localStorage.setItem("titan.skipAutoDemo", "1");
    }
    const sessionTitle = title.trim() || defaultTitle(agentPlay, game.label);
    // Always create as observe: API rejects mode=autonomous (Phase 4+). Learn-and-play uses
    // settings.play_enabled so the orchestrator + actions worker attach without that mode.
    const result = await createSession({
      game_slug: game.slug,
      game_profile_id: effectiveProfileId || undefined,
      title: sessionTitle,
      mode: "observe",
      settings: {
        agents_enabled: true,
        play_enabled: agentPlay,
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
        const recordingRaw = Reflect.get(started.data, "recording");
        const recording =
          typeof recordingRaw === "object" && recordingRaw !== null
            ? (recordingRaw as { state?: string; root_dir?: string })
            : null;
        const recordingActive =
          recording?.state === "recording" ||
          recording?.state === "starting" ||
          (recordOnStart && recording !== null);
        const recordingRoot =
          (typeof recording?.root_dir === "string" && recording.root_dir) ||
          (recordingActive && typeof dataDir === "string" && dataDir.length > 0
            ? `${dataDir}/recording`
            : null);
        const liveTitle = started.data.title?.trim() || sessionTitle;
        const attachRaw = Reflect.get(started.data, "play_attach");
        const attach =
          typeof attachRaw === "object" && attachRaw !== null
            ? (attachRaw as {
                backend?: string;
                ready?: boolean;
                message?: string;
                source?: string;
              })
            : null;
        const resolvedSource =
          Reflect.get(started.data, "session_source") === "live" ||
          Reflect.get(started.data, "session_source") === "fixture"
            ? (Reflect.get(started.data, "session_source") as "live" | "fixture")
            : sessionSource;
        const backend = (attach?.backend as PlayBackendKind | undefined) ?? null;
        dispatch(
          setActiveSession({
            id: started.data.id,
            title: liveTitle,
            recordingActive,
            recordingRootDir: recordingRoot,
            sessionSource: resolvedSource,
            playEnabled: agentPlay,
            playBackend: backend,
            playReady: typeof attach?.ready === "boolean" ? attach.ready : null,
            playAttachMessage: typeof attach?.message === "string" ? attach.message : null,
          }),
        );
        const kind =
          resolvedSource === "fixture"
            ? agentPlay
              ? "Fixture + HIL play"
              : "Fixture telemetry"
            : agentPlay
              ? `Live + ${backend ?? "play"}`
              : "Live install";
        const attachNote = attach?.message ? ` — ${attach.message}` : "";
        dispatch(showNotice(`${kind}: ${liveTitle}${attachNote}`));
        dispatch(closeSessionDialog());
        return;
      }
      const startMsg = formatApiError(started.error);
      setDialogError(`Session start failed: ${startMsg}`);
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
    setDialogError(`Could not create session: ${createMsg}`);
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
        {dialogError ? (
          <Alert
            severity="error"
            onClose={() => {
              setDialogError(null);
            }}
          >
            {dialogError}
          </Alert>
        ) : null}
        {gamesListFailed ? (
          <Alert severity="error">
            Could not load installs from the API: {formatApiError(gamesListError)}. You can still start a
            fixture session, or fix the API and click Retry below.
          </Alert>
        ) : null}
        {readinessFailed && agentPlay ? (
          <Alert severity="warning">Play readiness check failed: {formatApiError(readinessError)}</Alert>
        ) : null}
        <Typography variant="body2" color="text.secondary">
          Agents watch telemetry, write lessons, and (when play is on) propose controls that{" "}
          <code>titan-actions</code> executes via kRPC, SCS, or HIL.
        </Typography>
        <Alert severity={sessionSource === "live" ? "success" : "warning"} sx={{ width: "100%" }}>
          {sessionSource === "live" ? (
            "Live install selected — telemetry targets this profile; play attaches kRPC (KSP) or SCS (ETS2/ATS)."
          ) : (
            <>
              <strong>No game install on this PC yet.</strong> Sessions use fixture telemetry; agent play runs
              in software HIL only (no kRPC/SCS). Browse to your <code>{exeHint}</code> below to register an
              install for live telemetry and play.
            </>
          )}
        </Alert>
        {agentPlay && playAttach ? (
          <Alert
            severity={playAttach.ready ? (sessionSource === "live" ? "success" : "info") : "warning"}
            sx={{ width: "100%" }}
          >
            Play attach ({playAttach.backend}
            {sessionSource === "live" ? ", live" : ", fixture"}): {playAttach.message}
          </Alert>
        ) : null}
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
          <Alert severity="warning" variant="outlined" sx={{ width: "100%" }}>
            <Typography variant="subtitle2" gutterBottom>
              No install for {game?.label ?? gameSlug}
            </Typography>
            <Typography variant="body2" component="div">
              1. Click <strong>Browse &amp; register</strong> and pick <code>{exeHint}</code>.
              <br />
              2. Or open <strong>Game discovery</strong> to Scan + register multiple games.
              <br />
              Launch game and live kRPC/SCS play stay disabled until a profile exists.
            </Typography>
            <Stack direction="row" spacing={1} sx={{ mt: 1.5 }} flexWrap="wrap" useFlexGap>
              <Button
                variant="contained"
                size="small"
                disabled={registering || gamesListFailed}
                startIcon={<FolderOpenIcon />}
                onClick={() => void onBrowseAndRegister()}
              >
                Browse &amp; register
              </Button>
              <Button variant="outlined" size="small" onClick={onOpenGameDiscovery}>
                Open Game discovery
              </Button>
              {gamesListFailed ? (
                <Button variant="text" size="small" onClick={() => void refetchGames()}>
                  Retry API
                </Button>
              ) : null}
            </Stack>
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
              ? gameSlug === "ksp"
                ? "Starts titan-actions with TITAN_PLAY_BACKEND=krpc. Start KSP with the kRPC mod (RPC 50000 / stream 50001)."
                : "Starts titan-actions with TITAN_PLAY_BACKEND=scs (ViGEm on Windows, keyboard brake fallback)."
              : "Starts titan-actions with TITAN_PLAY_BACKEND=hil for software play without a game."}
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

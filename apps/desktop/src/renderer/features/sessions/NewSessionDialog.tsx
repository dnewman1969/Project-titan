import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import { useState } from "react";

import { useCreateSessionMutation, useStartSessionMutation } from "../../app/api";
import { useAppDispatch, useAppSelector } from "../../app/hooks";
import { showNotice } from "../operations/layoutSlice";
import { closeSessionDialog, setActiveSession } from "./sessionsSlice";

const GAMES = [
  { slug: "ksp", label: "Kerbal Space Program" },
  { slug: "ets2", label: "Euro Truck Simulator 2" },
  { slug: "ats", label: "American Truck Simulator" },
] as const;

function rtkMutationStatus(error: unknown): number | null {
  if (typeof error !== "object" || error === null || !("status" in error)) return null;
  const status = Reflect.get(error, "status");
  return typeof status === "number" ? status : null;
}

/** M7.T6 stub: creates a session when POST /sessions exists; otherwise explains the planned API. */
export function NewSessionDialog() {
  const open = useAppSelector((s) => s.sessions.dialog === "new");
  const dispatch = useAppDispatch();
  const [title, setTitle] = useState("Observe session");
  const [gameSlug, setGameSlug] = useState<(typeof GAMES)[number]["slug"]>("ksp");
  const [createSession, { isLoading: creating }] = useCreateSessionMutation();
  const [startSession, { isLoading: starting }] = useStartSessionMutation();

  const game = GAMES.find((g) => g.slug === gameSlug) ?? GAMES[0];
  const isLoading = creating || starting;
  const onClose = () => {
    dispatch(closeSessionDialog());
  };

  const onCreate = async () => {
    const sessionTitle = title.trim() || "Observe session";
    const result = await createSession({
      game_slug: game.slug,
      title: sessionTitle,
      mode: "observe",
      settings: { agents_enabled: true },
    });
    if ("data" in result && result.data) {
      const started = await startSession(result.data.id);
      if ("data" in started && started.data) {
        dispatch(
          setActiveSession({
            id: started.data.id,
            title: started.data.title,
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
    <Dialog open={open} onClose={onClose} aria-labelledby="new-session-title" maxWidth="xs" fullWidth>
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
            setGameSlug(e.target.value as (typeof GAMES)[number]["slug"]);
          }}
          fullWidth
        >
          {GAMES.map((g) => (
            <MenuItem key={g.slug} value={g.slug}>
              {g.label}
            </MenuItem>
          ))}
        </TextField>
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

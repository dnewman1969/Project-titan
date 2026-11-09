import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import { useState } from "react";

import { useCreateSessionMutation } from "../../app/api";
import { useAppDispatch, useAppSelector } from "../../app/hooks";
import { showNotice } from "../operations/layoutSlice";
import { closeSessionDialog } from "./sessionsSlice";

const GAMES = [
  { id: "ksp", profile: "ksp_default", label: "Kerbal Space Program" },
  { id: "ets2", profile: "ets2_default", label: "Euro Truck Simulator 2" },
  { id: "ats", profile: "ats_default", label: "American Truck Simulator" },
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
  const [gameId, setGameId] = useState<(typeof GAMES)[number]["id"]>("ksp");
  const [createSession, { isLoading }] = useCreateSessionMutation();

  const game = GAMES.find((g) => g.id === gameId) ?? GAMES[0];
  const onClose = () => {
    dispatch(closeSessionDialog());
  };

  const onCreate = async () => {
    const result = await createSession({
      game_id: game.id,
      game_profile_id: game.profile,
      title: title.trim() || "Observe session",
      mode: "observe",
    });
    if ("data" in result && result.data) {
      dispatch(showNotice(`Session created (${result.data.state}): ${result.data.title}`));
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
          value={gameId}
          onChange={(e) => {
            setGameId(e.target.value as (typeof GAMES)[number]["id"]);
          }}
          fullWidth
        >
          {GAMES.map((g) => (
            <MenuItem key={g.id} value={g.id}>
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

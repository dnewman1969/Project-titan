import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Typography from "@mui/material/Typography";

import { useAppDispatch, useAppSelector } from "../../app/hooks";
import { setFirstRunOpen, setKrpcObsHelpOpen } from "../operations/layoutSlice";

export function KrpcObsHelpDialog() {
  const dispatch = useAppDispatch();
  const open = useAppSelector((s) => s.layout.krpcObsHelpOpen);
  const close = () => dispatch(setKrpcObsHelpOpen(false));
  return (
    <Dialog open={open} onClose={close} aria-labelledby="krpc-obs-title" maxWidth="sm" fullWidth>
      <DialogTitle id="krpc-obs-title">kRPC and OBS</DialogTitle>
      <DialogContent>
        <Typography variant="subtitle1" component="h2" gutterBottom>
          kRPC (Kerbal Space Program)
        </Typography>
        <Typography variant="body2" color="text.secondary" component="p" sx={{ mb: 2 }}>
          Live Kerbal Space Program sessions use the kRPC 0.5.x mod. Titan reads flight data and sends control
          over TCP ports 50000 and 50001, instead of injecting keystrokes. Register KSP_x64.exe under Tools →
          Game discovery, then File → New session and pick that install. Turn on Agent play. The session chip
          stays on "waiting" until kRPC answers. A fixture session only plays demo telemetry and does not
          connect to kRPC.
        </Typography>
        <Typography variant="subtitle1" component="h2" gutterBottom>
          OBS Studio
        </Typography>
        <Typography variant="body2" color="text.secondary" component="p">
          Recording uses OBS Studio 30 or newer with obs-websocket v5 on port 4455. Record → Start recording
          always writes the session folder (manifest and timeline). When OBS is connected it also captures the
          game. The OBS pill in the status bar shows that websocket. If OBS is offline, recording still starts
          and the notice says capture is degraded. First-run setup walks through installing OBS.
        </Typography>
      </DialogContent>
      <DialogActions>
        <Button
          onClick={() => {
            close();
            dispatch(setFirstRunOpen(true));
          }}
        >
          Open first-run setup
        </Button>
        <Button variant="contained" onClick={close}>
          Close
        </Button>
      </DialogActions>
    </Dialog>
  );
}

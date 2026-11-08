import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Snackbar from "@mui/material/Snackbar";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import { MONO_FONT } from "@titan/ui-kit";

import { dismissNotice, setAboutOpen } from "../features/operations/layoutSlice";
import { OperationsCenter } from "../features/operations/OperationsCenter";
import { killAcknowledged } from "../features/safety/safetySlice";
import { useAppDispatch, useAppSelector } from "./hooks";
import { getTitan } from "./runtime";
import { useApiStatus } from "./useApiStatus";
import { useShellBridge } from "./useShellBridge";

function AboutDialog() {
  const dispatch = useAppDispatch();
  const open = useAppSelector((s) => s.layout.aboutOpen);
  const titan = getTitan();
  const rows: [string, string][] = [
    ["Titan", titan.versions.app],
    ["Electron", titan.versions.electron],
    ["Chromium", titan.versions.chrome],
    ["Node", titan.versions.node],
    ["API", titan.apiBase],
    ["Backend", titan.backend],
    ["Kill switch", titan.killHotkey],
  ];
  const close = () => dispatch(setAboutOpen(false));
  return (
    <Dialog open={open} onClose={close} aria-labelledby="about-title" maxWidth="xs" fullWidth>
      <DialogTitle id="about-title">About Titan</DialogTitle>
      <DialogContent>
        <Table size="small">
          <TableBody>
            {rows.map(([name, value]) => (
              <TableRow key={name}>
                <TableCell sx={{ color: "text.secondary", border: 0 }}>{name}</TableCell>
                <TableCell sx={{ fontFamily: MONO_FONT, border: 0 }}>{value}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </DialogContent>
      <DialogActions>
        <Button onClick={close}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}

function KillBanner() {
  const dispatch = useAppDispatch();
  const safety = useAppSelector((s) => s.safety);
  if (!safety.killed) return null;
  const at = safety.last_kill_at ? new Date(safety.last_kill_at).toLocaleTimeString() : "";
  return (
    <Alert
      severity="error"
      variant="filled"
      role="alert"
      sx={{
        position: "fixed",
        top: 64,
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 1300,
        minWidth: 460,
      }}
      action={
        <Button color="inherit" size="small" onClick={() => dispatch(killAcknowledged())}>
          Dismiss
        </Button>
      }
    >
      Kill switch engaged {at} ({safety.last_kill_source}). AI control is off; Phase 1 has no input path.
    </Alert>
  );
}

export function App() {
  useShellBridge();
  const status = useApiStatus();
  const dispatch = useAppDispatch();
  const notice = useAppSelector((s) => s.layout.notice);
  return (
    <>
      <OperationsCenter status={status} />
      <KillBanner />
      <AboutDialog />
      <Snackbar
        key={notice?.id}
        open={notice !== null}
        message={notice?.text}
        autoHideDuration={3500}
        onClose={() => dispatch(dismissNotice())}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      />
    </>
  );
}

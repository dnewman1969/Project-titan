import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Link from "@mui/material/Link";
import Step from "@mui/material/Step";
import StepLabel from "@mui/material/StepLabel";
import Stepper from "@mui/material/Stepper";
import Typography from "@mui/material/Typography";
import { useEffect, useState } from "react";

import { useAppDispatch, useAppSelector } from "../../app/hooks";
import { setFirstRunOpen } from "../operations/layoutSlice";

const STORAGE_KEY = "titan.firstRunComplete";

const STEPS = [
  {
    title: "Ollama",
    body: "Install Ollama and pull qwen3:8b. Titan blocks agent start when Ollama is down (model pill may show degraded).",
    href: "https://ollama.com/download",
  },
  {
    title: "OBS Studio",
    body: "Install OBS 30+ and enable obs-websocket v5 on port 4455. REC calls StartRecord when OBS is running, and shows OBS not running when it is not.",
    href: "https://obsproject.com/",
  },
  {
    title: "Memurai / Redis",
    body: "Run Memurai on 127.0.0.1:63790 with requirepass. Store the password in Titan secrets.",
    href: "https://www.memurai.com/get-memurai",
  },
] as const;

export function isFirstRunPending(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) !== "1";
  } catch {
    return false;
  }
}

export function markFirstRunComplete(): void {
  try {
    localStorage.setItem(STORAGE_KEY, "1");
  } catch {
    /* private mode */
  }
}

export function FirstRunWizard() {
  const dispatch = useAppDispatch();
  const forcedOpen = useAppSelector((s) => s.layout.firstRunOpen);
  const [dismissed, setDismissed] = useState(false);
  const [active, setActive] = useState(0);
  const step = STEPS[active] ?? STEPS[0];
  const open = !dismissed && (isFirstRunPending() || forcedOpen);

  useEffect(() => {
    if (open) dispatch(setFirstRunOpen(true));
  }, [dispatch, open]);

  const finish = () => {
    markFirstRunComplete();
    setDismissed(true);
    dispatch(setFirstRunOpen(false));
  };

  if (!open) return null;
  return (
    <Dialog open onClose={finish} aria-labelledby="first-run-title" maxWidth="sm" fullWidth>
      <DialogTitle id="first-run-title">First-run setup</DialogTitle>
      <DialogContent>
        <Stepper activeStep={active} sx={{ mb: 2 }}>
          {STEPS.map((s) => (
            <Step key={s.title}>
              <StepLabel>{s.title}</StepLabel>
            </Step>
          ))}
        </Stepper>
        <Typography variant="subtitle1" gutterBottom>
          {step.title}
        </Typography>
        <Typography variant="body2" color="text.secondary" component="p" sx={{ mb: 2 }}>
          {step.body}
        </Typography>
        <Link href={step.href} target="_blank" rel="noreferrer">
          Open download page
        </Link>
      </DialogContent>
      <DialogActions>
        <Button
          disabled={active === 0}
          onClick={() => {
            setActive((n) => n - 1);
          }}
        >
          Back
        </Button>
        {active < STEPS.length - 1 ? (
          <Button
            variant="contained"
            onClick={() => {
              setActive((n) => n + 1);
            }}
          >
            Next
          </Button>
        ) : (
          <Button variant="contained" onClick={finish}>
            Finish
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}

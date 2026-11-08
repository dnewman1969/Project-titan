# Hardware-in-the-loop checklist

Manual checks that CI cannot run (real games, OBS, webcam, GPU). Each milestone needs a signed-off
copy of its section in the PR before it can close. Record the PC, Windows build, GPU driver and
results.

## M0: Repository and toolchain

- [ ] On a clean Windows 11 machine, `pnpm i && uv sync && pnpm codegen && pnpm test` is green.
- [ ] `pnpm dev` opens the Titan window with all six main-screen panels and the full menu bar.
- [ ] The API status pill turns green with the API running, and red within 5 s of stopping it.
- [ ] `Ctrl+Shift+F12` shows the kill-switch notice (no-op in Phase 1).
- [ ] DevTools console shows no CSP violations.

## M1: Platform services and supervisor

- [ ] Cold start brings every service to healthy in under 20 s on the reference PC.
- [ ] Killing any child process restarts it in under 10 s with an event logged.
- [ ] Quitting the app leaves zero Titan processes (`tasklist | findstr /i titan` is empty).
- [ ] The telemetry bar shows live CPU, GPU, RAM and FPS; FPS shows `n/a` with no game running.

Later milestones (game discovery, telemetry, recording clap test, soak tests) add their sections here.

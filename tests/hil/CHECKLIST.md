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

CI covers the same flow headless (`tests/integration/test_supervisor_e2e.py` on Linux and Windows);
these checks cover the installed app on real hardware.

- [ ] Cold start brings every service to healthy in under 20 s on the reference PC (boot splash closes;
      Services pill green). Record the time from the window opening.
- [ ] First start creates `titan/postgres` in Credential Manager (`cmdkey /list | findstr titan`) and
      no password appears in `%LOCALAPPDATA%\Titan\logs`.
- [ ] Killing each child (`postgres.exe`, `chroma.exe`, the API's `python.exe`) in Task Manager restarts
      it in under 10 s with an event in the Event Log panel.
- [ ] Quitting the app leaves zero Titan processes: before, note the PIDs with
      `Get-CimInstance Win32_Process | ? { $_.CommandLine -match 'titan|chroma|pgsql' }`; after, the same
      command lists none.
- [ ] Ending the Electron process tree in Task Manager (a crash) also leaves zero processes within 5 s
      (supervisor parent watch, then the job object).
- [ ] Ending only `titan-supervisor`'s `python.exe` takes Postgres, Chroma and the API with it (job
      object), and Electron restarts the supervisor.
- [ ] The telemetry bar shows live CPU, RAM and GPU (NVIDIA: utilisation, VRAM, temperature);
      FPS shows `n/a` with no game running.
- [ ] With PresentMon bundled and Titan run as admin (or the user in Performance Log Users), FPS shows a
      live value while a game runs and `n/a` after it exits.
- [ ] `Ctrl+Shift+F12` shows the kill banner in under 100 ms and the API reports `killed: true`
      (`GET /api/v1/safety/state`); Resume clears it.

Later milestones (game discovery, telemetry, recording clap test, soak tests) add their sections here.

### Learn-and-play beta (software HIL vs this checklist)

- **Software HIL (CI / no game):** `uv run pytest tests/integration/test_learn_play_smoke.py` — New session → learn → play closed loop with mocked HIL (fixture attach). See [docs/learn-and-play-beta.md](../docs/learn-and-play-beta.md).
- **Reference PC happy path (after cloud smoke is green):** File → New session → agent play on → fixture/HIL or registered install → watch learn strip + Agent play attach → confirm throttle/brake changes in-game for live attach. Record install paths and kRPC/SCS readiness; do not treat software HIL as a substitute for these rows.

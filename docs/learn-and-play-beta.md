# Learn-and-play beta (in-repo)

How the closed loop works today, without a separate “please test” playbook. Use this on a **Windows gaming PC** with real installs when you are ready; use **software HIL** everywhere else (CI, Linux, no game).

## Beta bar

Agents **learn** (discoveries + lessons on the blackboard, reinforced after `action.executed`) and **play** (real drivers when the game and backends are available). Success on a real install means: live telemetry → salient events → play proposal → game control actually changes state → lesson written → optional REC timeline row.

Until that happens on **your** KSP or ETS2/ATS install, treat production paths as integration targets, not claims.

## End-to-end flow

1. **Start Titan** — `Start-Titan.bat` / `.ps1` (see root `README.md`).
2. **Discover game** — Operations Center → scan installs; pick game + profile in **New session**.
3. **Agent play** — New session defaults to **Enable agent play (learn-and-play beta)** (starts `titan-orchestrator` with play + `titan-actions`). Mode is `autonomous` when play is on.
4. **Learn** — orchestrator `session_loops` writes `discoveries` / `lessons`; play feedback loop records outcomes from `action.executed`. Failed actions adapt later proposals (gentler throttle / stronger brake) via session `PlayMemory`.
5. **REC** — top bar **REC** (or **Record with session** on create) writes `manifest.json` + `timeline.ndjson` under `%LOCALAPPDATA%/Titan/sessions/<id>/recording/`. Play actions and lesson learn events append timeline rows when REC is on.

### Demo path (no game)

`VITE_TITAN_AUTO_DEMO=1` still uses fixture telemetry. For honest play without a game:

```powershell
$env:TITAN_PLAY_BACKEND = "hil"
pnpm dev
```

Or run the integration test:

```powershell
uv run pytest tests/integration/test_play_hil_loop.py
```

HIL does **not** touch the game; it updates in-memory state and optional `hil.ndjson` (see `services/actions/README.md`).

## Real KSP (kRPC)

| Step    | Detail                                                                |
| ------- | --------------------------------------------------------------------- |
| Mod     | kRPC 0.5.x in `GameData/kRPC` (pinned in `third_party/manifest.yaml`) |
| Server  | RPC `50000`, stream `50001`, `127.0.0.1`, auto-accept                 |
| Titan   | New session → KSP install → **agent play** → start (optional launch)  |
| Driver  | `TITAN_PLAY_BACKEND=auto` (default) + `TITAN_GAME_SLUG=ksp`           |
| Actions | `ksp.throttle`, `ksp.stage`, `ksp.sas`, `ksp.rcs`, `ksp.brake`        |

If kRPC is down, `action.executed` reports `ok: false` with a connect error (no fake success).

Env overrides: `TITAN_KRPC_HOST`, `TITAN_KRPC_RPC_PORT`, `TITAN_KRPC_STREAM_PORT`.

## Real ETS2 / ATS (SCS)

| Step      | Detail                                                                                                   |
| --------- | -------------------------------------------------------------------------------------------------------- |
| Telemetry | scs-sdk plugin (read via shared memory — Windows)                                                        |
| Control   | ViGEm virtual gamepad (`scs.brake` / `scs.throttle` triggers), else keyboard brake (`S`) via `SendInput` |
| Titan     | New session → truck sim → **agent play** → game focused                                                  |

Linux dev hosts cannot drive SCS; use HIL or a Windows machine.

## Session artifacts

| Path                                  | Contents                                                           |
| ------------------------------------- | ------------------------------------------------------------------ |
| `<session>/play.ndjson`               | Every play attempt (when `TITAN_SESSION_DATA_DIR` set)             |
| `<session>/recording/manifest.json`   | REC metadata                                                       |
| `<session>/recording/timeline.ndjson` | `recording.*`, `play.action`, `lesson.proposed`, `lesson.feedback` |
| Blackboard `lessons` / `discoveries`  | Crew learnings (UI agents panel / WS)                              |

## Hardware checklist vs software HIL

- **Software HIL** — `TITAN_PLAY_BACKEND=hil`, pytest integration test above; no Windows/game required.
- **Hardware HIL** — manual sign-off for OBS, GPU, soak tests: `tests/hil/CHECKLIST.md` (add learn-and-play rows when validating on the reference PC).

## Related code

- `services/actions/titan_actions/drivers/` — kRPC, SCS, HIL
- `services/orchestrator/titan_orchestrator/play_policy.py` — event → proposal
- `services/orchestrator/titan_orchestrator/session_loops.py` — telemetry, learn, feedback
- `services/actions/README.md` — backend env table

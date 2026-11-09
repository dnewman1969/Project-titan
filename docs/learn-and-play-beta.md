# Learn-and-play beta (in-repo)

How the closed loop works today, without a separate “please test” playbook. Use this on a **Windows gaming PC** with real installs when you are ready; use **software HIL** everywhere else (CI, Linux, no game).

## Beta bar

Agents **learn** (discoveries + lessons on the blackboard, reinforced after `action.executed`) and **play** (real drivers when the game and backends are available). Success on a real install means: live telemetry → salient events → play proposal → game control actually changes state → lesson written → optional REC timeline row.

Until that happens on **your** KSP or ETS2/ATS install, treat production paths as integration targets, not claims.

## End-to-end flow

1. **Start Titan** — `Start-Titan.bat` / `.ps1` (see root `README.md`).
2. **Discover game** — **View → Games** (or **Open Game discovery** from New session when no install): **Scan**, or **Browse…** `KSP_x64.exe` → **Register install path**. Then **File → New session** and pick that installation (Operations Center scan also lists installs).
3. **Agent play** — New session defaults to **Enable agent play (learn-and-play beta)** (`mode=observe` + `settings.play_enabled`; starts `titan-orchestrator` with play + `titan-actions`). Top bar **Agent play** switch toggles play on a live session (`POST /sessions/{id}/play`). With a **registered install**, start attaches an explicit backend (`krpc` for KSP, `scs` for ETS2/ATS). Without an install, source is **fixture** and play attaches **HIL**. New session, game window, and top bar show live vs fixture + readiness.
4. **Learn** — orchestrator `session_loops` writes `discoveries` / `lessons`; play feedback loop records outcomes from `action.executed`. Ops Center **AI Agents** panel shows a **Learn loop** strip (discoveries, lessons, outcomes). Failed actions adapt later proposals (gentler throttle / stronger brake) via session `PlayMemory`. Telemetry rules in `games/ksp/events.yaml` and `games/ets2/events.yaml` emit salient events (`ksp.launch`, `vehicle.speeding`, `vehicle.collision`, …); `play_policy.py` maps them to `ksp.*` / `scs.*` actions executed by the real kRPC or ViGEm drivers when attach is `krpc`/`scs` (not only HIL).
5. **REC** — top bar **REC** (or **Record with session** on create) writes `manifest.json` + `timeline.ndjson` under `%LOCALAPPDATA%/Titan/sessions/<id>/recording/`. Without OBS, beta still allocates **stub tracks** under `recording/tracks/` and a `video.stub` timeline row; with OBS on `:4455`, tracks mark `source=obs`. Top bar **OBS** pill + Webcam panel show capture state (`GET /capture/obs`). Play actions, lessons, and commentary append timeline rows when REC is on. Session `play_attach.json` records the backend probe.

### Demo path (no game)

`VITE_TITAN_AUTO_DEMO=1` still uses fixture telemetry. For honest play without a game:

```powershell
$env:TITAN_PLAY_BACKEND = "hil"
pnpm dev
```

Or run the cloud learn→play smoke (New session → learn → HIL play → feedback):

```powershell
uv run pytest tests/integration/test_learn_play_smoke.py
```

HIL does **not** touch the game; it updates in-memory state and optional `hil.ndjson` (see `services/actions/README.md`).

## Real KSP (kRPC)

| Step    | Detail                                                                                                   |
| ------- | -------------------------------------------------------------------------------------------------------- |
| Mod     | kRPC 0.5.x in `GameData/kRPC` (pinned in `third_party/manifest.yaml`)                                    |
| Server  | RPC `50000`, stream `50001`, `127.0.0.1`, auto-accept                                                    |
| Titan   | New session → KSP install → **agent play** → start (optional launch)                                     |
| Driver  | `TITAN_PLAY_BACKEND=auto` (default) + `TITAN_GAME_SLUG=ksp`                                              |
| Actions | `ksp.fly` (throttle + SAS or autopilot pitch/heading), plus thrust/stage/RCS/brakes/gear and `ksp.steer` |

With play on and the game set to KSP, the orchestrator runs a **flight loop** (about 1 Hz) on the latest telemetry frame. It publishes `ksp.fly`: kRPC's built-in autopilot holds pitch and heading 90° east (gravity turn after 250 m, throttle eased through high dynamic pressure, full throttle and nose-up if the vessel is low and descending, throttle idle and SAS once apoapsis is above 80 km or the craft is in orbit). That is the same hold as the kRPC launch-into-orbit tutorial and kOS `lock steering to heading()`. kOS and MechJeb are not required. The first pre-launch tick also stages once so the engine actually lights. If the scene is not flight, or the frame has no vessel, the loop writes a blackboard discovery (`flight.no_vessel` / `flight.waiting`) and does not send controls. Proposals land in `lessons` (`play.flight.*`) and outcomes in `lessons` (`feedback.*`), which the desktop learn strip already polls.

If kRPC is down, `action.executed` reports `ok: false` with a connect error (no fake success). Live telemetry retries the port instead of exiting.

Env overrides: `TITAN_KRPC_HOST`, `TITAN_KRPC_RPC_PORT`, `TITAN_KRPC_STREAM_PORT`.

## Real ETS2 / ATS (SCS)

| Step      | Detail                                                                                                             |
| --------- | ------------------------------------------------------------------------------------------------------------------ |
| Telemetry | scs-sdk plugin (read via shared memory — Windows)                                                                  |
| Control   | ViGEm virtual X360 (`scs.brake` / `scs.throttle` triggers; no physical pad), else keyboard `S`/`W` via `SendInput` |
| Titan     | New session → truck sim → **agent play** → game focused                                                            |

Linux dev hosts cannot drive SCS; use HIL or a Windows machine.

## Session artifacts

| Path                                  | Contents                                                                               |
| ------------------------------------- | -------------------------------------------------------------------------------------- |
| `<session>/play.ndjson`               | Every play attempt (when `TITAN_SESSION_DATA_DIR` set)                                 |
| `<session>/recording/manifest.json`   | REC metadata                                                                           |
| `<session>/recording/timeline.ndjson` | `recording.*`, `play.action`, `lesson.proposed`, `lesson.feedback`, `agent.commentary` |
| Blackboard `lessons` / `discoveries`  | Crew learnings (UI agents panel / WS)                                                  |
| Chroma `memories` on session stop     | Persists learnings; **AI → Memory Browser** to search/add/delete                       |
| Session start `prior.*` notes         | Top prior memories seeded into blackboard for the same `game_slug`                     |

## Hardware checklist vs software HIL

- **Software HIL** — `TITAN_PLAY_BACKEND=hil`, pytest integration test above; no Windows/game required.
- **Hardware HIL** — manual sign-off for OBS, GPU, soak tests: `tests/hil/CHECKLIST.md` (add learn-and-play rows when validating on the reference PC).

## YouTube publish stub

**Tools → YouTube Publish** opens the Ops Center dialog. Connect stub auth (`POST /accounts/youtube/connect`, no Google OAuth), create a **private** draft upload job for the active session, approve, then run the stub uploader (fake Studio URL). Real OAuth / resumable upload remains Phase 7.

## Related code

- `services/actions/titan_actions/drivers/` — kRPC, SCS, HIL
- `services/orchestrator/titan_orchestrator/play_policy.py` — event → proposal
- `services/orchestrator/titan_orchestrator/flight_policy.py` — continuous KSP heading hold
- `services/orchestrator/titan_orchestrator/session_loops.py` — telemetry, learn, flight loop, feedback
- `services/api/titan_api/youtube_stub.py` — YouTube auth + draft upload stubs
- `services/actions/README.md` — backend env table

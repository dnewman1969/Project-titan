# titan-actions

Sole input owner for Project Titan (Section 6.9). Learn-and-play beta routes `action.propose` messages from the session bus into game drivers.

## Backends (`TITAN_PLAY_BACKEND`)

| Value            | Use                                                                                                          |
| ---------------- | ------------------------------------------------------------------------------------------------------------ |
| `auto` (default) | `ksp` → kRPC (`127.0.0.1:50000/50001`); `ets2`/`ats` → ViGEm virtual X360 (no physical pad), else keyboard W/S |
| `krpc`           | Force kRPC (KSP)                                                                                               |
| `scs`            | Force SCS path (ViGEm preferred, keyboard fallback)                                                            |
| `hil`            | **Honest HIL:** in-memory state + optional `hil.ndjson` trace — no game attached                               |
| `keyboard`       | Force SCS keyboard path on Windows (`W` throttle / `S` brake via SendInput)                                    |

Also set `TITAN_PLAY_HIL=1` to force HIL.

Environment set by the session controller when play is enabled:

- `TITAN_GAME_SLUG` — from the session game
- `TITAN_KRPC_HOST`, `TITAN_KRPC_RPC_PORT`, `TITAN_KRPC_STREAM_PORT`

## Actions

- **KSP (kRPC):** `ksp.throttle`, `ksp.stage`, `ksp.sas`, `ksp.rcs`, `ksp.brake`
- **SCS:** `scs.brake`, `scs.throttle`

Failed kRPC/SCS connections return `ok: false` on `action.executed` (no silent stub success).

## HIL / ViGEm tests

```bash
TITAN_PLAY_BACKEND=hil uv run pytest tests/integration/test_learn_play_smoke.py
uv run pytest services/actions/tests/test_scs_driver.py
```

Cloud CI mocks ViGEm via `ScsDriver(pad_factory=...)`. On a Windows PC with ETS2/ATS + ViGEmBus, use `auto`/`scs`; without ViGEm, keyboard W/S still drives.

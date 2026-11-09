# Developer setup

How to build, test and run Titan on a Windows 11 development machine. Linux works for everything
except Windows-only features (game capture, SCS shared memory, the NSIS installer). The
[architecture spec](titan-architecture-spec.md) is the source of truth; this page covers only the
mechanics.

## 1. Prerequisites

Install these once. Run the commands in PowerShell.

| Tool            | Version                         | Install                                                                                |
| --------------- | ------------------------------- | -------------------------------------------------------------------------------------- |
| Git and Git LFS | current                         | `winget install Git.Git GitHub.GitLFS`, then `git lfs install`                         |
| Node.js         | 22.12+ (`.nvmrc` → 22; 24.x OK) | `winget install OpenJS.NodeJS.LTS`, or nvm-windows with `nvm install 22`               |
| pnpm            | 10.33.4 (`packageManager`)      | `corepack enable` (bundled with Node), then `corepack prepare pnpm@10.33.4 --activate` |
| uv              | 0.13.7 or newer                 | `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"`  |
| Python          | 3.12 (`.python-version`)        | `uv python install 3.12` (uv also installs it on first `uv sync`)                      |
| Docker Desktop  | optional                        | Only for `docker-compose.yml`; see section 3 for native alternatives                   |

Visual Studio Build Tools are **not** needed: every Python and Node dependency ships Windows wheels or
prebuilt binaries.

## 2. Clone, install, test

```powershell
git clone https://github.com/dnewman1969/Project-titan.git
cd Project-titan
pnpm i                  # Node workspace (apps/*, packages/ts/*)
uv sync                 # Python workspace (packages/py/*, services/*) into .venv
pnpm codegen            # regenerate schemas/ and packages/ts/protocol from the Pydantic models
pnpm test               # Vitest + pytest
pnpm lint               # ruff, mypy, import boundaries, eslint, prettier, tsc
```

`pnpm test` passes without any services: database and service tests skip when nothing is listening.
Set `TITAN_REQUIRE_POSTGRES=1` and `TITAN_REQUIRE_SERVICES=1` to make them fail instead, as CI does.
`TITAN_REQUIRE_SUPERVISOR_E2E=1` also runs the M1 acceptance test
(`tests/integration/test_supervisor_e2e.py`), which needs PostgreSQL 16 binaries and a Redis with
`requirepass` (`TITAN__REDIS__PASSWORD`).

The first `pnpm dev` downloads the Electron binary (about 110 MB) into `node_modules/electron/dist`.

## 3. Backing services

`titan-supervisor` (M1) starts everything in the order `postgres, redis, chroma, migrate, api`.
Postgres and Chroma each run in one of two modes (`config/titan.yaml`, `mode:`):

- **managed** (the default, and what users get): the supervisor runs portable PostgreSQL 16 (D1) and
  Chroma as its own children, restarts them when they die and stops them on quit. On first start it
  runs `initdb` with a random superuser password stored in Windows Credential Manager as
  `titan/postgres`. Data lives under `%LOCALAPPDATA%\Titan\data`.
- **external**: something else runs the service on the configured port (Docker, a native install); the
  supervisor only health-checks it.

Redis is always external: users install Memurai (D5), configured with `requirepass`. The Redis check
reports `degraded` when the server accepts clients without a password.

**With Docker (ADR 0020):** `tools/dev-up.ps1` (or `tools/dev-up.sh`) runs `docker compose up` and
sets external mode plus the throwaway dev passwords:

```powershell
docker compose up -d --wait          # postgres:16.15 :54329, redis:7.4.12 :63790 (requirepass), chroma 1.5.9 :8766
$env:TITAN__POSTGRES__MODE = "external"; $env:TITAN__CHROMA__MODE = "external"
$env:TITAN__POSTGRES__PASSWORD = "titan"; $env:TITAN__REDIS__PASSWORD = "titan-dev"
```

**Without Docker (managed):** `.\tools\dev-up.ps1 -Managed`. You need:

- **PostgreSQL 16 binaries:** `uv run python tools/fetch-third-party.py postgresql --extract` puts the
  portable build under `third_party/cache/postgresql/pgsql/bin`, which the supervisor finds on its
  own (or set `TITAN__POSTGRES__BIN_DIR`). Nothing needs to be installed or running.
- **Redis:** Memurai Developer (<https://www.memurai.com/get-memurai>) on port 63790 with
  `requirepass`. Store the password once with
  `uv run python -c "from titan_core.secrets import set_secret; set_secret('redis', input())"`,
  or set `TITAN__REDIS__PASSWORD`.
- **Chroma:** nothing; the supervisor runs `chroma` from the venv, or `uvx --from chromadb==1.5.9 chroma`.

Secrets come from the OS keyring (service `titan`, entries `postgres` and `redis`) unless
`TITAN__POSTGRES__PASSWORD` / `TITAN__REDIS__PASSWORD` are set. On Linux without a keyring, set the
environment variables. The ports match `config/titan.yaml`. Every setting can be overridden with
`TITAN__<SECTION>__<KEY>` environment variables (Section 9.5).

## 4. Run the app

```powershell
.\tools\dev-up.ps1                   # docker compose up, then pnpm dev
.\tools\dev-up.ps1 -NoCompose        # containers you already started
.\tools\dev-up.ps1 -Managed          # no Docker: portable Postgres and Chroma under the supervisor
pnpm dev                             # just the app, with whatever TITAN__* settings you exported
```

`pnpm dev` starts electron-vite with hot reload. The Electron main process generates a per-launch
bearer token and starts `uv run titan-supervisor` with it (and its own PID, so the supervisor exits
if Electron dies). The supervisor brings up the services, runs migrations and starts the API; a boot
splash shows progress. Its output appears in the terminal prefixed `[supervisor]`. The status bar
shows API, database and services health, the telemetry bar shows live CPU/GPU/RAM/FPS over the
WebSocket gateway, and `Ctrl+Shift+F12` engages the kill switch through `POST /safety/kill`.
Quitting the app stops every child.

To run the backend on its own, for example under a debugger:

```powershell
$env:TITAN_LAUNCH_TOKEN = "dev-token"
$env:TITAN__API__CORS_ORIGINS = '["app://titan","http://localhost:5173"]'
uv run titan-supervisor              # everything; status at http://127.0.0.1:8769/status (bearer token)
uv run titan-api                     # or only the API: http://127.0.0.1:8765/api/v1/docs
# in a second shell, with the same TITAN_LAUNCH_TOKEN set, `pnpm dev` uses this backend instead
```

Set `TITAN_BACKEND=none` to start the shell without any backend.

## 5. Common tasks

| Task                                     | Command                                                                                                   |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| Regenerate protocol schemas and TS types | `pnpm codegen` (CI fails if you forget)                                                                   |
| New migration                            | add a revision under `packages/py/titan-db/titan_db/migrations/versions/`, then `uv run titan-db upgrade` |
| Roll back migrations                     | `uv run titan-db downgrade`                                                                               |
| Format everything                        | `pnpm format`                                                                                             |
| Python tests with coverage               | `uv run pytest --cov`                                                                                     |
| Fetch pinned third-party binaries        | `uv run python tools/fetch-third-party.py --list`, then `... postgresql ffmpeg --extract`                 |
| Build the Windows installer              | `pnpm --filter @titan/desktop dist` (output in `apps/desktop/release/`)                                   |
| Pre-commit hooks                         | `uvx pre-commit install`                                                                                  |

## 6. Tools needed by later milestones

Install these when you start the milestone that needs them; Titan's first-run wizard (M10.T4) does the
same for users.

| Tool                                   | Needed from | Notes                                                                         |
| -------------------------------------- | ----------- | ----------------------------------------------------------------------------- |
| Ollama                                 | M3          | `winget install Ollama.Ollama`; listens on `127.0.0.1:11434`. Pull `qwen3:8b` |
| Memurai                                | M1.T2       | Redis 7 API on `127.0.0.1:63790` with `requirepass`                           |
| OBS Studio 30+                         | M8          | Enable obs-websocket v5 under Tools > WebSocket Server Settings               |
| Kerbal Space Program 1.12 + kRPC 0.5.4 | M4/M5       | Pinned in `third_party/manifest.yaml`; Titan installs it after consent        |
| ETS2/ATS + scs-sdk-plugin 1.12.1       | M4/M5       | Pinned DLL hash in `third_party/manifest.yaml`                                |
| NVIDIA driver with NVML                | M1.T6       | GPU metrics; other GPUs show `n/a`                                            |
| PresentMon 2.x console                 | M1.T6       | Game FPS. Needs admin or the Performance Log Users group (D18); else `n/a`    |

## 7. Branch protection (repository settings)

Configure `main` under GitHub Settings > Branches (Section 9.3):

- Require a pull request with **1 approving review**, and review from code owners (`.github/CODEOWNERS`).
- Require status checks to pass, and require branches to be up to date. Required checks: `lint`,
  `codegen-check / codegen-check`, `test-py-linux`, `test-ts`, `test-windows`.
- Require linear history (squash merge only), and block force pushes and deletions.
- Enable Dependabot alerts and security updates (`.github/dependabot.yml` runs weekly).

PR titles use Conventional Commits with the task ID, for example `feat(api): M1.T4 WS gateway skeleton`.

## 8. Milestone stubs (M8 through M10)

CI does not require OBS, Ollama or a real game. Use these when you want tomorrow-style manual testing:

| Milestone     | Local entry point                                                                             | Offline tests                                                                                                |
| ------------- | --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| M8 Capture    | `ObsClient` in `services/capture/titan_capture/obs.py`                                        | `uv run pytest services/capture/tests/test_obs_respx.py`                                                     |
| M9 Memory     | Session stop → Chroma upsert; **AI → Memory Browser**; `memory.search` / `memory.write` tools | `uv run pytest packages/py/titan-memory/tests/test_learnings.py services/api/tests/test_memory_learnings.py` |
| M10 Installer | `pnpm --filter @titan/desktop dist`                                                           | NSIS shell build only until `installer/build-*.ps1` lands                                                    |

When you have OBS running, enable obs-websocket v5 and confirm the API dependency pill shows `obs: up`.

## 9. Troubleshooting

- **`Electron failed to install correctly`:** delete `node_modules/electron` and run
  `pnpm --filter @titan/desktop exec install-electron`.
- **Port already in use:** another service is on 8765, 54329, 63790 or 8766. Stop it, or override the
  port with the matching `TITAN__…__PORT` variable.
- **API pill stays red in `pnpm dev`:** check the `[supervisor]` lines in the terminal. The usual cause
  is `uv` missing from `PATH` in the shell that started `pnpm dev`.
- **Database pill red:** Postgres is not reachable with the configured port and password; see section 3.
  In managed mode the server log is `%LOCALAPPDATA%\Titan\logs\postgres\postgres.log`.
- **Services pill shows `redis degraded`:** Redis accepts clients without a password; set
  `requirepass` (section 3).
- **`the cluster exists but the keyring has no titan/postgres password`:** the managed data directory
  was created with a password that is no longer in Credential Manager. Set
  `TITAN__POSTGRES__PASSWORD`, or delete `%LOCALAPPDATA%\Titan\data\pg` to start over.

## Learn-and-play beta

Closed-loop agent play, HIL (no game), and real KSP / ETS2 paths are documented in
[learn-and-play-beta.md](learn-and-play-beta.md). Hardware sign-off remains in
[tests/hil/CHECKLIST.md](../tests/hil/CHECKLIST.md).

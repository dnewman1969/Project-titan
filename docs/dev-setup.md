# Developer setup

How to build, test and run Titan on a Windows 11 development machine. Linux works for everything
except Windows-only features (game capture, SCS shared memory, the NSIS installer). The
[architecture spec](titan-architecture-spec.md) is the source of truth; this page covers only the
mechanics.

## 1. Prerequisites

Install these once. Run the commands in PowerShell.

| Tool            | Version                    | Install                                                                                |
| --------------- | -------------------------- | -------------------------------------------------------------------------------------- |
| Git and Git LFS | current                    | `winget install Git.Git GitHub.GitLFS`, then `git lfs install`                         |
| Node.js         | 22 LTS (`.nvmrc`)          | `winget install OpenJS.NodeJS.LTS`, or nvm-windows with `nvm install 22`               |
| pnpm            | 10.33.4 (`packageManager`) | `corepack enable` (bundled with Node), then `corepack prepare pnpm@10.33.4 --activate` |
| uv              | 0.13.7 or newer            | `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 \| iex"`  |
| Python          | 3.12 (`.python-version`)   | `uv python install 3.12` (uv also installs it on first `uv sync`)                      |
| Docker Desktop  | optional                   | Only for `docker-compose.yml`; see section 3 for native alternatives                   |

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

The first `pnpm dev` downloads the Electron binary (about 110 MB) into `node_modules/electron/dist`.

## 3. Backing services

M0 code needs only PostgreSQL 16; Redis and Chroma are used by the integration tests. From M1 the
supervisor manages portable Postgres itself (D1), and users install Memurai (D5).

**With Docker (ADR 0020):**

```powershell
docker compose up -d --wait          # postgres:16.15 :54329, redis:7.4.12 :63790, chroma 1.5.9 :8766
$env:TITAN__POSTGRES__PASSWORD = "titan"
uv run titan-db upgrade              # apply migrations to the dev database
```

**Without Docker:**

- **PostgreSQL 16:** install from <https://www.enterprisedb.com/downloads/postgres-postgresql-downloads>
  and create a `titan` login with the CREATEDB privilege. Either run it on port 54329 or set
  `TITAN__POSTGRES__PORT=5432`. Set `TITAN__POSTGRES__PASSWORD` to that login's password.
- **Redis:** Memurai Developer (<https://www.memurai.com/get-memurai>) configured for port 63790.
- **Chroma:** `uvx --from chromadb==1.5.9 chroma run --host 127.0.0.1 --port 8766 --path $env:LOCALAPPDATA\Titan\dev\chroma`

The ports match `config/titan.yaml`. Every setting can be overridden with `TITAN__<SECTION>__<KEY>`
environment variables (Section 9.5).

## 4. Run the app

```powershell
.\tools\dev-up.ps1                   # docker compose up, migrate, then pnpm dev
.\tools\dev-up.ps1 -NoServices       # same, with services you started yourself
pnpm dev                             # just the app
```

`pnpm dev` starts electron-vite with hot reload. The Electron main process generates a per-launch
bearer token and starts the API (`uv run titan-api`) with it. The status bar shows the API and
database health; the menus and `Ctrl+Shift+F12` kill switch are wired.

To run the API on its own, for example under a debugger:

```powershell
$env:TITAN_LAUNCH_TOKEN = "dev-token"
$env:TITAN__API__CORS_ORIGINS = '["app://titan","http://localhost:5173"]'
uv run titan-api                     # http://127.0.0.1:8765/api/v1/docs
# in a second shell, with the same TITAN_LAUNCH_TOKEN set, `pnpm dev` uses this API instead
```

Set `TITAN_BACKEND=none` to start the shell without any API.

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
| Memurai                                | M1.T2       | Redis 7 API on `127.0.0.1:63790`                                              |
| OBS Studio 30+                         | M8          | Enable obs-websocket v5 under Tools > WebSocket Server Settings               |
| Kerbal Space Program 1.12 + kRPC 0.5.4 | M4/M5       | Pinned in `third_party/manifest.yaml`; Titan installs it after consent        |
| ETS2/ATS + scs-sdk-plugin 1.12.1       | M4/M5       | Pinned DLL hash in `third_party/manifest.yaml`                                |
| NVIDIA driver with NVML                | M1.T6       | GPU metrics; other GPUs show `n/a`                                            |

## 7. Branch protection (repository settings)

Configure `main` under GitHub Settings > Branches (Section 9.3):

- Require a pull request with **1 approving review**, and review from code owners (`.github/CODEOWNERS`).
- Require status checks to pass, and require branches to be up to date. Required checks: `lint`,
  `codegen-check / codegen-check`, `test-py-linux`, `test-ts`, `test-windows`.
- Require linear history (squash merge only), and block force pushes and deletions.
- Enable Dependabot alerts and security updates (`.github/dependabot.yml` runs weekly).

PR titles use Conventional Commits with the task ID, for example `feat(api): M1.T4 WS gateway skeleton`.

## 8. Troubleshooting

- **`Electron failed to install correctly`:** delete `node_modules/electron` and run
  `pnpm --filter @titan/desktop exec install-electron`.
- **Port already in use:** another service is on 8765, 54329, 63790 or 8766. Stop it, or override the
  port with the matching `TITAN__…__PORT` variable.
- **API pill stays red in `pnpm dev`:** check the `[api]` lines in the terminal. The usual cause is `uv`
  missing from `PATH` in the shell that started `pnpm dev`.
- **Database pill red:** Postgres is not reachable with the configured port and password; see section 3.

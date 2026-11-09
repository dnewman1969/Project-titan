# Beta test playbook — download, run, and report

Use this on **`main`** (Phase 1: M4–M10 testable slice — sessions, recording manifest + REC control, memory search API, agent voice demo).  
There is **no standalone installer build required** for this test — you run from source like a developer.

Target OS for the full experience: **Windows 11**. Linux works for API/tests; game adapters and the installer are Windows-oriented.

---

## Part A — Get the code onto your PC

### Option 1 — Git clone (recommended)

1. Install **Git** and **Git LFS** (Windows: `winget install Git.Git GitHub.GitLFS`, then `git lfs install`).
2. Open **PowerShell** and run:

```powershell
cd $HOME
git clone https://github.com/dnewman1969/Project-titan.git titan-test
cd titan-test
git checkout main
git pull
```

You should see recent commits mentioning M6/M7 merge and `docs/fof-studio-integration-ideas.md`.

### Option 2 — Zip/tarball (USB or second PC)

On a machine that already has the repo:

```powershell
cd path\to\Project-titan
.\tools\export-test-tree.sh $HOME\Desktop\titan-export   # Git Bash or WSL on Windows
```

Copy `project-titan-*.tar.gz` to the test PC, extract, then continue from **Part B** inside that folder.

**Note:** The tarball does **not** include `node_modules` or `.venv`; you still run install steps below.

---

## Part B — One-time prerequisites

Install each once (Windows / PowerShell unless noted).

| Tool           | How                                                                                                                  |
| -------------- | -------------------------------------------------------------------------------------------------------------------- |
| Node 22        | `winget install OpenJS.NodeJS.LTS`                                                                                   |
| pnpm 10        | `corepack enable` then `corepack prepare pnpm@10.33.4 --activate`                                                    |
| uv             | `powershell -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/install.ps1 \| iex"`                                |
| Python 3.12    | `uv python install 3.12` (or let `uv sync` install it)                                                               |
| Docker Desktop | Optional; simplifies Postgres + Redis (see Part C)                                                                   |
| Memurai        | If **not** using Docker: [Memurai Developer](https://www.memurai.com/get-memurai), port **63790**, set `requirepass` |

Close and reopen PowerShell after installs so `node`, `pnpm`, and `uv` are on `PATH`.

---

## Part C — Install dependencies

**Fast path (Windows):**

```powershell
cd path\to\Project-titan
.\tools\setup-windows-test.ps1
.\tools\dev-up.ps1 -NoCompose
```

`setup-windows-test.ps1` runs `pnpm install`, `uv sync`, `pnpm codegen`, and starts Docker Compose when Docker is installed.

**Manual path** — in the repo root (`Project-titan`):

```powershell
pnpm install
uv sync
pnpm codegen
```

First run can take several minutes (Electron download ~110 MB on first `pnpm dev`).

### Backing services (pick one path)

**Path C1 — Docker (easiest if you have Docker)**

```powershell
docker compose up -d --wait
$env:TITAN__POSTGRES__MODE = "external"
$env:TITAN__CHROMA__MODE = "external"
$env:TITAN__POSTGRES__PASSWORD = "titan"
$env:TITAN__REDIS__PASSWORD = "titan-dev"
```

**Path C2 — Managed Postgres (no Docker)**

```powershell
uv run python tools/fetch-third-party.py postgresql --extract
# Memurai on 63790 with password — set once:
$env:TITAN__REDIS__PASSWORD = "your-memurai-password"
.\tools\dev-up.ps1 -Managed
```

**Path C3 — You already ran dev-up**

```powershell
.\tools\dev-up.ps1              # Docker + dev
# or
.\tools\dev-up.ps1 -Managed     # portable Postgres + supervisor-managed Chroma
```

### Seed the database (personas, games)

With Postgres reachable:

```powershell
uv run python tools/seed-dev-db.py
```

You should see counts for personas, games, and teams.

---

## Part D — Start the application

### Standard (supervisor + Electron UI)

From repo root:

```powershell
.\tools\dev-up.ps1
# or, if containers are already up:
.\tools\dev-up.ps1 -NoCompose

# If you only use managed mode and already ran -Managed once:
pnpm dev
```

What to expect:

1. Terminal shows `[supervisor]` lines (postgres, redis, migrate, api).
2. **Electron** opens with a boot splash, then the **Operations Center**.
3. Top/status area should move toward **API up** / **database up** (give it 30–60 seconds).
4. Quitting the app stops child processes.

### Optional: API only (troubleshooting)

```powershell
$env:TITAN_LAUNCH_TOKEN = "dev-token"
$env:TITAN__API__CORS_ORIGINS = '["app://titan","http://localhost:5173"]'
uv run titan-supervisor
```

Open http://127.0.0.1:8765/api/v1/docs in a browser (you need the launch token from the supervisor/Electron logs for authenticated routes).

### Optional: agent voice / portraits

Create `apps/desktop/.env` (or set in the shell before `pnpm dev`):

```env
VITE_OWL_TTS_URL=http://127.0.0.1:8790
VITE_COMFYUI_VIEW_URL=http://127.0.0.1:8188/view
```

If unset, **Brag / Roast** still work via **Windows speech synthesis**.

---

## Part E — What to test (checklist)

Do these in order. For each item, note **PASS / FAIL / SKIP** and one line of what you saw.

### E1 — App shell and health

| #   | Action                     | Pass if                                                    |
| --- | -------------------------- | ---------------------------------------------------------- |
| 1   | App opens without crashing | Main grid visible (top bar, game area, panels)             |
| 2   | Boot splash clears         | Not stuck on “Starting…”                                   |
| 3   | Status / pills             | API and Postgres show healthy (not stuck red)              |
| 4   | Menu **Help → About**      | Version dialog opens                                       |
| 5   | Menu **View** toggles      | Panels hide/show; layout should persist after refresh (M7) |

### E2 — Games API (M4)

With API up, in PowerShell (replace `TOKEN` with launch token from supervisor log if needed; dev often uses env `TITAN_LAUNCH_TOKEN`):

```powershell
$headers = @{ Authorization = "Bearer dev-token" }   # if you set dev-token
Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/v1/games" -Headers $headers
```

| #   | Pass if                                                                      |
| --- | ---------------------------------------------------------------------------- |
| 6   | HTTP 200 and items include slugs like `ksp`, `ets2`, `ats`                   |
| 7   | **View → toggle Games** (if present) or games panel shows discovery skeleton |

### E3 — Sessions (M6 + M7)

| #   | Action                             | Pass if                                         |
| --- | ---------------------------------- | ----------------------------------------------- |
| 8   | **File → New Session** (or Ctrl+N) | Dialog opens                                    |
| 9   | Create session with KSP            | “Live session” notice; top bar chip shows title |
| 10  | Top bar after create               | Session chip filled (not “No session”)          |

### E3b — Recording (M8)

| #   | Action                  | Pass if                                                                  |
| --- | ----------------------- | ------------------------------------------------------------------------ |
| 11  | Click **REC** (red dot) | “Recording started” notice; label shows **REC ON**                       |
| 12  | Click **REC** again     | Stops; notice says stopped                                               |
| 13  | Optional: OBS on 4455   | No error in API log; manifest still written if OBS offline (degraded OK) |

Manifest path is returned by the API under the session `data_dir/recording/manifest.json`.

### E3c — Memory API (M9 stub)

```powershell
$h = @{ Authorization = "Bearer $($env:TITAN_LAUNCH_TOKEN)" }
Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/v1/memory/status" -Headers $h
Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/v1/memory/search" -Method POST -Headers $h -ContentType "application/json" -Body '{"query":"ksp launch"}'
```

| #   | Pass if                                                                     |
| --- | --------------------------------------------------------------------------- |
| 14  | `/memory/status` returns chroma state JSON                                  |
| 15  | `/memory/search` returns `items` array (may be empty if Chroma has no data) |

### E4 — Agents voice demo

| #   | Action                          | Pass if                                          |
| --- | ------------------------------- | ------------------------------------------------ |
| 16  | **Brag** button                 | New chat line + you hear speech (browser or Owl) |
| 17  | **Roast me**                    | Arrogant line + speech                           |
| 18  | Tap a crew chip (Wernher, etc.) | Greeting line appears                            |
| 19  | Type in chat box and Send       | Agent replies with smack-talk flavor             |
| 20  | Avatar “speaking” ring          | Visible while audio plays                        |

### E5 — Telemetry (M5, optional)

If you created a session id `S`:

1. Set `VITE_TITAN_DEMO_SESSION=S` in `apps/desktop/.env`, restart `pnpm dev`.
2. Or replay a fixture (no game):

```powershell
uv run python -m titan_telemetry replay games/ksp/fixtures/launch-to-orbit.ndjson
```

| #   | Pass if                                                                      |
| --- | ---------------------------------------------------------------------------- |
| 21  | Telemetry bar shows **Speed** (or values change) when demo session + WS work |
| 22  | Event log gains lines when WS events flow                                    |

### E6 — Safety

| #   | Action                   | Pass if                                   |
| --- | ------------------------ | ----------------------------------------- |
| 23  | Press **Ctrl+Shift+F12** | Kill switch engages; banner/state updates |
| 24  | Resume if offered        | Returns to normal                         |

### E7 — First-run wizard (M10 stub)

| #   | Pass if                                                               |
| --- | --------------------------------------------------------------------- |
| 25  | First-run wizard appears (or can be opened from tools menu if linked) |
| 26  | Links open (Ollama, Memurai, etc.) without crashing the app           |

### E8 — Automated smoke (optional but helpful)

```powershell
pnpm test
uv run pytest -q
```

| #   | Pass if                                                                                                 |
| --- | ------------------------------------------------------------------------------------------------------- |
| 27  | TS tests pass; most Python tests pass (Redis integration may fail if Memurai not on 63790 — note if so) |

---

## Part F — Report back to the agent

Copy this template into your next message:

```
## Environment
- OS:
- Path: (clone / tarball)
- Docker or Managed:
- Memurai / Redis: yes/no, port:

## Results
E1:
E2:
E3:
E4:
E5:
E6:
E7:
E8:

## Blockers
- (anything that stopped you before E4)

## Wow / bugs
- What impressed you:
- What broke or felt wrong (steps to reproduce):
- Screenshots or log snippets if any:

## Wishes for next build
- (priority 1–3)
```

---

## Part G — Known limits (not bugs)

- **No packaged NSIS installer** yet for daily use — dev workflow only unless you build `pnpm --filter @titan/desktop dist` yourself.
- **OBS** improves M8 capture when obs-websocket v5 is on **4455**; without OBS, REC still writes **manifest.json** (degraded).
- **Live agent bus chat** (full M7.T2 streaming) is not wired; Agents panel is a **demo** until WS chat lands.
- **YouTube publish kit** is documented from FoF research, not yet a button in the UI.
- **Ollama** optional for this test; missing Ollama may show degraded model pill, not a crash.

---

## Quick reference

| Item              | Value                                                                            |
| ----------------- | -------------------------------------------------------------------------------- |
| API               | http://127.0.0.1:8765/api/v1                                                     |
| API docs          | http://127.0.0.1:8765/api/v1/docs                                                |
| Supervisor status | http://127.0.0.1:8769/status                                                     |
| More detail       | [dev-setup.md](./dev-setup.md), [local-test-package.md](./local-test-package.md) |

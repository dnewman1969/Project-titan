# Download and test Project Titan on another machine

## Quick export (same machine or copy via USB/cloud)

From the repo root:

```bash
chmod +x tools/export-test-tree.sh
./tools/export-test-tree.sh ~/titan-export
```

This writes `~/titan-export/project-titan-<timestamp>.tar.gz` (no `node_modules`, `.venv`, or git history).

Copy that file to the machine you will test on, then:

```bash
mkdir -p ~/titan-test && tar xzf project-titan-*.tar.gz -C ~/titan-test
cd ~/titan-test/Project-titan   # or the folder name inside the tarball
```

## Full clone (recommended if you use Git)

```bash
git clone https://github.com/dnewman1969/Project-titan.git ~/titan-test
cd ~/titan-test
git checkout main
```

## Install and run

Follow [dev-setup.md](./dev-setup.md) for Postgres, Redis, `uv sync`, and `pnpm install`.

Minimal smoke:

```bash
pnpm lint && pnpm test:ts
TITAN_REQUIRE_POSTGRES=1 uv run pytest -q
pnpm --filter @titan/desktop dev
```

## Agent voice and ComfyUI portraits (optional)

In `apps/desktop/.env` or your shell:

| Variable                   | Purpose                                                              |
| -------------------------- | -------------------------------------------------------------------- |
| `VITE_OWL_TTS_URL`         | Base URL for Owl TTS / OwlAI HTTP API (e.g. `http://127.0.0.1:8790`) |
| `VITE_COMFYUI_VIEW_URL`    | Comfy `view` endpoint base for generated portraits                   |
| `VITE_AGENT_PORTRAIT_BASE` | Static CDN/folder of `/{persona_slug}.png`                           |
| `VITE_TITAN_DEMO_SESSION`  | Session UUID for live telemetry WebSocket demo                       |

Without Owl TTS, the desktop falls back to the browser **Speech Synthesis** API for demos.

Place portrait PNGs at `apps/desktop/public/portraits/wernher.png` (etc.) or point ComfyUI output filenames to `titan-{slug}.png`.

## Windows installer

When `main` CI is green on `build-installer`, download the artifact from the GitHub Actions run on `main` (workflow **CI** → job **build-installer**).

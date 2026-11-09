# Project Titan

Project Titan is a local-first, autonomous AI gaming content studio: a desktop application (Electron, React, TypeScript) backed by a Python FastAPI service and local models via Ollama, in which a team of cooperating AI agents sharing a blackboard memory researches a game, plays it, records the session with webcam and microphone, produces live commentary, and turns the result into edited videos, thumbnails and SEO metadata ready for publishing, with the human creator always in control of the final publish decision.

See [docs/titan-architecture-spec.md](docs/titan-architecture-spec.md) for the architecture specification.

## Quick start (Windows)

**Double-click `Start-Titan.bat` in this folder** (or run `Start-Titan.ps1` in PowerShell).

That script checks Node/pnpm/uv, fetches portable PostgreSQL on first run, ensures Redis on `127.0.0.1:63790` (Memurai or one Docker Redis container), then opens the **Operations Center**. No Kerbal install needed for the built-in demo — fixture telemetry and the crew talk on a live session automatically.

Prerequisites once: [Node 22](https://nodejs.org/), [uv](https://docs.astral.sh/uv/), and either **Memurai Developer** (Redis, port **63790**, password **titan-dev**) or Docker Desktop (only for Redis if Memurai is absent). Postgres and Chroma are started by Titan — not by Docker.

For contributor setup and architecture, see [docs/dev-setup.md](docs/dev-setup.md). For the learn-and-play beta (HIL + real KSP/truck installs), see [docs/learn-and-play-beta.md](docs/learn-and-play-beta.md).

## Repository map

| Path            | What it is                                                                                                           |
| --------------- | -------------------------------------------------------------------------------------------------------------------- |
| `apps/desktop`  | Electron + React Operations Center                                                                                   |
| `services/*`    | Python services: `api` (FastAPI), plus supervisor, orchestrator, telemetry, capture, workers, actions                |
| `packages/py/*` | Shared Python: `titan-core` (config, logging, IDs, clock, errors, protocol models), `titan-db` (migrations) and more |
| `packages/ts/*` | `@titan/protocol` (generated types and zod validators), `@titan/ui-kit` (theme and primitives)                       |
| `schemas/`      | Generated JSON Schemas for the agent message envelope, payloads, telemetry, WebSocket and events                     |
| `config/`       | Default configuration (`titan.yaml`, models, safety, recording, egress)                                              |
| `docs/`         | Architecture spec, [ADRs](docs/adr/README.md), developer setup                                                       |
| `tools/`        | Codegen, third-party fetcher, import-boundary lint, dev scripts                                                      |
| `third_party/`  | Pinned, hash-verified third-party binaries (downloaded, never committed)                                             |

Licensed under the [Apache License 2.0](LICENSE).

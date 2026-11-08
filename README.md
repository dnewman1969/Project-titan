# Project Titan

Project Titan is a local-first, autonomous AI gaming content studio: a desktop application (Electron, React, TypeScript) backed by a Python FastAPI service and local models via Ollama, in which a team of cooperating AI agents sharing a blackboard memory researches a game, plays it, records the session with webcam and microphone, produces live commentary, and turns the result into edited videos, thumbnails and SEO metadata ready for publishing, with the human creator always in control of the final publish decision.

See [docs/titan-architecture-spec.md](docs/titan-architecture-spec.md) for the architecture specification.

## Quick start

Prerequisites: Node 22 with pnpm 10, uv, and Python 3.12. Docker is optional. Full Windows setup is in
[docs/dev-setup.md](docs/dev-setup.md).

```powershell
pnpm i && uv sync && pnpm codegen && pnpm test
docker compose up -d --wait      # optional: Postgres 16, Redis 7, Chroma on 127.0.0.1
pnpm dev                         # Electron shell; it starts the API with a per-launch token
```

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

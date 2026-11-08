# Project Titan: Architecture and Implementation Specification v1.0

> **PREAMBLE (paste-ready; read first)**
>
> You are the **Lead Systems Architect and Principal Engineer for Project Titan**, an autonomous, local-first AI gaming content studio. You are one of the Project Titan coding workers building it in the project's GitHub repository. This document is the build spec. It lives in the repo at `docs/titan-architecture-spec.md` and is the source of truth for every worker. Follow it exactly. Where it is silent, choose the simplest option that fits its principles (Section 2.1) and record the choice as an Architecture Decision Record (ADR) in `docs/adr/NNNN-title.md`. If you must deviate from a decision in this spec, add an ADR in the same pull request and update this spec there too, so the spec and the code never disagree.
>
> **Build Phase 1 first.** Implement milestones M0 to M10 (Section 8.2) in order. A milestone is done only when its acceptance criteria pass in CI, or on the hardware checklist where CI cannot run them. Do not start Phase 2 work until the Phase 1 exit criteria pass. Phases 2 to 8 are described so that Phase 1 interfaces leave room for them. Do not implement them early.
>
> Non-negotiables: everything runs on one Windows 11 gaming PC with no cloud dependency. Every model call goes through the model-provider abstraction (Section 2.9). Every game goes through the game-adapter interface (Section 2.10), so adding a game never changes core code. In Phase 1 agents can read telemetry and talk, but they **cannot send any input to the game**. A human approves every publish. Use the schemas in Sections 4 to 7 verbatim unless an ADR changes them.
>
> Keywords: **MUST** means mandatory, **SHOULD** means default unless an ADR says otherwise, **MAY** means optional.

---

## How coding workers use this spec

- **Repository.** All code lives in the Project Titan GitHub monorepo (layout in Section 3). This spec is `docs/titan-architecture-spec.md`. ADRs are `docs/adr/`. The GitHub repo is the backup and the system of record: nothing counts as done until it is pushed.
- **Unit of work.** Each task in Section 8.2 has an ID (`M<milestone>.T<n>`). One task maps to one branch and one pull request. Put the ID in the branch name and PR title (for example `m5-t2-krpc-adapter`, "M5.T2: kRPC adapter streams"). Keep PRs small and stay inside the task. Ask the coordinator before taking a dependent task whose predecessor has not merged.
- **Definition of done.** CI is green (Section 9.3). The task's acceptance criteria are covered by automated tests, or by a filled-in hardware checklist entry (`tests/hil/CHECKLIST.md`) when they need a real game, GPU, or webcam. Generated code (Section 9.1) is regenerated and committed. Any decision the spec did not cover has an ADR.
- **Changing the spec.** Edit this file in a PR, with an ADR when a decision changes. Never let code and spec drift. Section numbers and schema names are referenced by other workers, so add new sections instead of renumbering.
- **Never commit:** secrets, tokens, `.env` files with values, recordings, model weights, Postgres or Chroma data, or third-party binaries (OBS, Ollama, Memurai, PostgreSQL, FFmpeg). These are fetched by `tools/fetch-third-party` from pinned URLs and SHA-256 hashes in `third_party/manifest.yaml`. Telemetry fixtures over 5 MB go through Git LFS.

## Table of contents

0. Decision register
1. Product summary and PRD essentials
2. Technical architecture
3. Repository structure
4. Data model: PostgreSQL schema and ChromaDB design
5. API contracts: REST and WebSocket
6. Agent communication protocol
7. Telemetry integration (KSP, ETS2, ATS)
8. Phased implementation plan and risk register
9. Engineering standards: code, tests, CI, configuration, observability, security
10. Appendices: default teams and personas, glossary

---

## 0. Decision register

These calls are final for v1. Each one gets an ADR in `docs/adr/` during M0.

| # | Decision | Chosen | Rejected | Why |
|---|---|---|---|---|
| D1 | Structured database | PostgreSQL 16, bundled portable binaries, Titan-managed | SQLite | Many processes write at once (API, orchestrator, telemetry host, Celery workers). Postgres gives row-level concurrency, JSONB with GIN indexes, `LISTEN/NOTIFY`, partial and generated-column indexes, and LangGraph's official Postgres checkpointer. SQLite's single writer would become the bottleneck at the first concurrent session. |
| D2 | Vector store | ChromaDB 0.6+/1.x in client-server mode on localhost | FAISS, pgvector | Chroma gives persistence, metadata filtering, and collection management out of the box. FAISS is only an index: no metadata filter, no persistence, no server. Server mode is required because Chroma's embedded `PersistentClient` is not safe across processes. Everything goes through the `VectorStore` interface, so pgvector stays a config-only swap later. |
| D3 | Embeddings | `sentence-transformers` with `BAAI/bge-small-en-v1.5` (384-d) on **CPU** | GPU embeddings, Ollama embeddings | Keeps VRAM free for the game and the LLM. About 5 ms per chunk on a modern CPU is enough. The model name is stored in each collection's metadata, and changing it triggers a re-index. |
| D4 | Message bus and realtime fan-out | Redis Streams (plus pub/sub only for the kill switch) | ZeroMQ, NATS | Redis is already required by Celery. Streams give ordered, replayable, persistent logs with consumer groups, which the WebSocket gateway needs for resume-from-sequence. |
| D5 | Redis on Windows | **Memurai** (native Windows, Redis 7 API) as a Windows service on `127.0.0.1:63790` | Docker/WSL2 Redis | No VM overhead on a gaming PC. Only `REDIS_URL` is used, so swapping to WSL2 Redis or Garnet is config-only. Its license is checked before distribution (risk R9). |
| D6 | Background jobs | Celery 5.4 with Redis broker. Windows pools: `threads` for I/O queues, `solo` for GPU and media queues | Dramatiq, arq | Celery is in the user's stack. Its prefork pool does not work on Windows, so Titan runs one process per queue class with an explicit pool (Section 2.7). |
| D7 | Orchestration | LangGraph `StateGraph`. One graph per agent role plus a Director graph, all hosted as asyncio tasks in **one orchestrator process per live session**, with Postgres checkpointing | One process per agent | Single GPU, single game: in-process routing is fast and simple. Redis Streams is the boundary to other processes, so scaling out later means adding consumer groups. |
| D8 | LLM runtime | Ollama (user-installed, `127.0.0.1:11434`) behind `ModelProvider`. Second built-in provider: any OpenAI-compatible server (llama.cpp, LM Studio, vLLM) | Hard-coding Ollama | Keeps Titan model-agnostic. Each agent role maps to a model in `models.yaml`. |
| D9 | Phase 1 model residency | **One** resident chat model shared by all roles (`OLLAMA_MAX_LOADED_MODELS=1`) | One model per role | Swapping models costs 2 to 10 s and VRAM spikes cause game stutter. Per-role routing exists but defaults to the same tag until VRAM profile "24 GB+" is selected. |
| D10 | Recording | OBS Studio 30+ driven over **obs-websocket v5** for gameplay video and audio tracks. Titan's capture worker runs **FFmpeg** for the webcam as a separate file | Custom DXGI recorder in Phase 1 | OBS already does game capture, NVENC, and multi-track lossless audio reliably. Webcam goes to a separate file to meet the "independent tracks" rule. Titan owns the webcam device and gives the UI an MJPEG preview. |
| D11 | In-app game view | Electron `desktopCapturer` preview of the game window (display only, never recorded) | Streaming OBS output into the app | Zero encode cost and no extra plugin. |
| D12 | KSP telemetry | **kRPC** 0.5.x mod (protobuf over TCP 50000/50001) | Telemachus | kRPC has streams, a maintained Python client, and a **control API** that Phase 4 uses instead of keyboard injection, which is safer. |
| D13 | ETS2/ATS telemetry | SCS Telemetry SDK through the community **scs-sdk-plugin** (RenCloud, pinned version) exposing shared memory `Local\SCSTelemetry`, read by a versioned Python layout parser | Writing our own C++ plugin in Phase 1 | Proven in both games with documented layout. Titan validates the plugin revision and refuses unknown layouts. Our own plugin is revisited in Phase 4 (ADR). |
| D14 | Schema source of truth | Pydantic v2 models in `packages/py/titan-core/protocol`. JSON Schema and TypeScript types are **generated** from them | Hand-written TypeScript | One definition. CI fails if generated files drift. |
| D15 | Python and Node toolchains | Python 3.12 with `uv` workspaces; Node 22 LTS with `pnpm` workspaces; Electron 33+ with `electron-vite` | Poetry, npm | Fast, lockfile-exact, monorepo-native. |
| D16 | Packaging | `electron-builder` NSIS installer. Ships embedded CPython 3.12 plus a frozen venv, portable PostgreSQL 16, and Chroma. Ollama, OBS, and Memurai are installed by a first-run wizard with links and version checks | PyInstaller | PyInstaller is fragile with torch, chromadb, and Celery. The venv approach is reproducible. |
| D17 | Game input (Phase 4) | One `titan-actions` process owns all input. API-level control first (kRPC). Virtual gamepad (ViGEmBus via `vgamepad`) for SCS games. `SendInput` keyboard and mouse last | PyAutoGUI everywhere | One choke point for the kill switch, rate limits, and foreground checks. PyAutoGUI is kept only for menu macros. |
| D18 | Game FPS metric | PresentMon (Intel, MIT) console mode in the supervisor. It reads ETW, so the user needs administrator rights or membership of the Performance Log Users group; otherwise FPS shows `n/a`. GPU metrics via NVML; non-NVIDIA shows `n/a` in v1 | Injecting an overlay | No injection into game processes, which keeps anti-cheat safe. |
| D19 | IDs and time | UUIDv7 primary keys generated by the app. All timestamps `timestamptz` UTC. One **session monotonic clock** (`time.perf_counter_ns`, backed by Windows QPC) stamps every event, frame, message, and track start | Database-generated IDs | IDs sort by time, and every artifact lines up on one timeline for editing. |

---

## 1. Product summary and PRD essentials

### 1.1 Vision
Titan is a desktop application that turns one gaming PC into an autonomous AI gaming studio. It researches a game, builds a specialised team of AI agents for it, watches and later plays the game, records everything (gameplay, webcam, microphone, agent voices) on separate tracks, produces commentary from a cast of AI characters, edits a draft video, generates thumbnails and SEO metadata, and publishes to YouTube **after human approval**. It learns from each session and from audience metrics. Everything runs locally and the user owns all data.

### 1.2 Users
| Persona | Primary need | Phase where served |
|---|---|---|
| Creator | Produce and publish more with less editing | 6 to 7 (Phase 1: recording) |
| Hobbyist | Watch AI play, experiment, build custom agents | 1, 3 |
| Researcher | Inspect multi-agent behaviour, memory, learning | 1 (full message and blackboard logs), 8 |
| Streamer | AI co-hosts with entertaining live commentary | 1 (text), 5 (voice and avatars) |

### 1.3 Objectives, mapped to phases
| Objective | Description | Phase |
|---|---|---|
| O1 | Understand a game automatically | 2 |
| O2 | Create game-specific agent teams | 3 (Phase 1 uses static templates from the game adapter) |
| O3 | Play autonomously | 4 |
| O4 | Record all activity on separate tracks | 1 |
| O5 | Generate entertaining content | 1 (text chat), 5 |
| O6 | Produce editable videos | 6 |
| O7 | Publish with one click after approval | 7 |
| O8 | Learn from previous sessions | 1 (memory DB, session logs), 8 |

### 1.4 Phase 1 scope
**In scope.** Electron Operations Center UI with menus, game view, agents panel, webcam panel, telemetry bar, and event log. Local LLMs through Ollama. Multi-agent framework (Director, blackboard, message bus, commentary floor control). Game discovery for Steam, Epic, and GOG. Adapters for **KSP 1.12.x, ETS2, ATS**. Telemetry ingest and normalization. Game event detection. Gameplay recording through OBS. Webcam and microphone recording. Session recording manifest. Memory database (Postgres plus Chroma) with end-of-session success log, failure log, discoveries, and lessons. Replay mode, which runs a recorded session's telemetry without the game.

**Out of scope for Phase 1.** Any game input. Web research. Dynamic agent generation. Computer vision for control. TTS and avatars. Video editing. Thumbnails. Publishing. These are interfaces only: tables and enums exist, endpoints may return `501`.

**Phase 1 deliverable (from source):** the user launches a game from Titan, agents discuss the game while reading live telemetry, the user watches it all in the Operations Center, and the session is recorded and remembered.

### 1.5 End-to-end workflow (target state)
```
Select game -> Discover install -> Research (P2) -> Knowledge base -> Agent Factory (P3)
 -> Training sim (P3/P4) -> Gameplay session (P1 observe / P4 act) -> Recording (P1)
 -> Video assembly (P6) -> Thumbnails (P7) -> SEO (P7) -> USER REVIEW -> Publish (P7)
 -> Analytics ingest -> Self-improvement (P8) -> loops back to Research/Agents
```

### 1.6 Success metrics (Phase 1 targets on the reference PC)
| Metric | Target |
|---|---|
| Game FPS impact with 5 agents live and OBS recording at 1080p60 | 10% or less versus the game alone (PresentMon average over 10 minutes) |
| Telemetry frame, adapter to UI | p95 under 250 ms |
| Game event to first commentary token in the UI | p50 under 1.5 s, p95 under 3 s |
| 2-hour soak | 0 crashes. Recovery from a killed worker in under 10 s. No recording gaps over 1 s |
| Recording track sync drift | 40 ms or less across a 2-hour session |
| Commentary repetition (near-duplicate utterances, cosine over 0.92, in a 10-minute window) | 5% or less |

### 1.7 Non-functional requirements
- **Local-first:** works fully offline once models are pulled. Network access is limited to an allowlist (Section 9.7) and only Phase 2 research and Phase 7 publish workers use it.
- **Recovery:** every process is supervised with restart backoff. LangGraph checkpoints each agent step. Sessions resume after an orchestrator crash with the blackboard intact.
- **Extensibility:** games, model providers, agent tools, and personas are plugins or config. Core code does not branch on a game ID.
- **Resource governance:** the game has priority. Titan lowers its own load when game FPS drops (Section 2.9.4).
- **Hardware scaling:** CPU fallback for every model role. Multi-GPU through provider routing (a role can pin to a GPU-specific Ollama instance). Distributed workers later through Redis.

### 1.8 Reference hardware
- **Minimum:** Windows 11 23H2+, 8-core CPU, 32 GB RAM, NVIDIA RTX 3060 12 GB, NVMe SSD with 200 GB free.
- **Recommended:** 12+ core CPU, 64 GB RAM, RTX 4080 16 GB / 4090 24 GB, separate recording drive.
- AMD and Intel GPUs: LLMs through Ollama work. NVENC is replaced by AMF or QSV in the OBS profile. GPU telemetry shows `n/a` in v1.

---

## 2. Technical architecture

### 2.1 Principles
1. **Blackboard-centred.** Agents never call each other directly. They post envelopes to the bus and read and write the session blackboard. The Director coordinates.
2. **The game comes first.** Titan must not make the game unplayable. Resource guard and safety rails come before features.
3. **Everything is an event on one clock.** Telemetry, game events, agent messages, and track starts all carry `t_mono_ns`, so editing and analysis line up exactly.
4. **Read-only before write.** Observe (P1), then assist (P3), then act (P4), each behind explicit capability flags.
5. **Plugins, not branches.** Games, model providers, tools, and personas are discovered through Python entry points and YAML manifests.
6. **Postgres is the source of truth.** Chroma and the Redis caches can always be rebuilt from Postgres and session files.

### 2.2 Process topology (one Windows PC)
```
+--------------------------------------------------------------------------------------+
|                               Windows 11 gaming PC                                    |
|                                                                                      |
|  +-------------------------- Electron app (Titan.exe) -----------------------------+ |
|  |  Main process: window mgmt, globalShortcut (kill switch), spawns supervisor,     | |
|  |                desktopCapturer (game preview), auto-update off by default        | |
|  |  Renderer (React/MUI/Redux): Operations Center UI. Talks ONLY to titan-api       | |
|  +-----------------------------|----------------------------------------------------+ |
|                                | HTTP REST + 1 WebSocket (127.0.0.1:8765, bearer)    |
|  +-----------------------------v---------------+     +----------------------------+  |
|  | titan-api (FastAPI/uvicorn)                 |     | titan-supervisor (Python)  |  |
|  |  REST, WS gateway, StreamPersister,         |<--->| starts/health-checks/      |  |
|  |  session controller, settings               |     | restarts all processes,    |  |
|  +----|-------------|--------------|-----------+     | PresentMon, NVML, psutil   |  |
|       | SQL         | XADD/XREAD   | Celery send     +----------------------------+  |
|  +----v-----+  +----v-----------------------------+  +----------------------------+  |
|  | Postgres |  | Redis-compatible (Memurai :63790)|  | ChromaDB server :8766      |  |
|  | :54329   |  | Streams = bus/telemetry/events   |  | collections (Sec 4.3)      |  |
|  +----^-----+  | Celery broker+results, caches    |  +-------------^--------------+  |
|       |        +--^-----------^-----------^-------+                |                 |
|       |           |           |           |                        |                 |
|  +----+-----------+--+  +-----+---------+ |  +---------------------+--------------+  |
|  | titan-orchestrator|  | titan-telemetry| |  | Celery workers                     |  |
|  | (1 per live sess.)|  | (adapter host) | |  |  worker-io   (threads: default,    |  |
|  | Director + agents |  | GameAdapter    | |  |               research, publish)   |  |
|  | LangGraph, Floor  |  | normalize,     | |  |  worker-gpu  (solo: llm_batch,     |  |
|  | Manager, LLM      |  | event detect   | |  |               vision, embed)       |  |
|  | Scheduler         |  +--^-------------+ |  |  worker-media(solo: media)          |  |
|  +---------|---------+     | kRPC TCP /    |  +-------------------------------------+  |
|            | HTTP          | shared memory |                                           |
|  +---------v---------+  +--+------------+  +--+-------------+  +-------------------+  |
|  | Ollama :11434     |  | GAME PROCESS  |  | titan-capture  |  | titan-actions (P4)|  |
|  | (user-installed)  |  | KSP / ETS2 /  |  | OBS ws client, |  | sole input owner, |  |
|  | GPU               |  | ATS + plugin  |  | FFmpeg webcam, |  | kill switch, rate |  |
|  +-------------------+  +---------------+  | MJPEG preview  |  | limits            |  |
|                                            +--+-------------+  +-------------------+  |
|                                               | obs-websocket :4455                    |
|                                            +--v-------------+                          |
|                                            | OBS Studio 30+ |                          |
|                                            +----------------+                          |
+--------------------------------------------------------------------------------------+
```

### 2.3 Process catalogue
| Process | Tech | Listens | Responsibilities | Restart policy |
|---|---|---|---|---|
| `Titan.exe` (Electron main) | Electron 33+, TS | none | Window, menus, kill-switch global shortcut, spawns `titan-supervisor`, passes the launch token to the renderer through preload | User restarts |
| Renderer | React 18, MUI 6, Redux Toolkit plus RTK Query, Recharts | none | Operations Center UI | Reload on crash |
| `titan-supervisor` | Python asyncio | `127.0.0.1:8769` (internal API, Section 5.2 "Supervisor RPC") | Start order, health checks, exponential restart backoff (1s, 2s, 4s, max 30s, circuit-break after 5 failures in 2 min), PresentMon, NVML, psutil sampling into the `titan:sys:metrics` stream, tree-kills children when Electron exits (on Windows a `KILL_ON_JOB_CLOSE` job object that the supervisor joins at startup, so even a hard kill of the supervisor takes every child with it) | Restarted by Electron |
| `titan-api` | FastAPI, uvicorn (1 worker), SQLAlchemy 2 async plus asyncpg | `127.0.0.1:8765` | REST, WebSocket gateway, session controller (spawns and stops orchestrator, telemetry, and capture through the supervisor RPC), StreamPersister (Redis to Postgres) | Supervisor |
| `titan-orchestrator` | Python asyncio, LangGraph | none | Director, agent runtimes, blackboard service, Floor Manager, LLM Scheduler, memory retrieval | Supervisor. Resumes from checkpoint |
| `titan-telemetry` | Python, adapter plugins | none | Loads the `GameAdapter`, connects to the game, normalizes frames, detects events, writes raw frame files | Supervisor. Reconnect loop |
| `titan-capture` | Python, `obsws-python`, FFmpeg 7 | `127.0.0.1:8767` (MJPEG webcam preview) | OBS control, webcam recording, recording manifest, markers | Supervisor |
| `titan-worker-io` | Celery `-P threads -c 8` | none | Queues `default`, `research`, `publish` | Supervisor |
| `titan-worker-gpu` | Celery `-P solo` | none | Queues `llm_batch`, `embed`, `vision` | Supervisor. Paused by Resource Guard while a session is live and FPS is degraded |
| `titan-worker-media` | Celery `-P solo` | none | Queue `media` (remux, proxies, render) | Supervisor |
| `titan-actions` (P4) | Python, `ctypes` SendInput, `vgamepad`, kRPC | none | Sole input owner. Safety rails (Section 6.9) | Supervisor. Starts **disarmed** |
| PostgreSQL 16 | portable binaries | `127.0.0.1:54329` | Source of truth | Supervisor (`pg_ctl`) |
| Memurai (Redis 7) | Windows service | `127.0.0.1:63790` | Bus, broker, cache | Windows service, health-checked |
| ChromaDB | `chroma run` | `127.0.0.1:8766` | Vector index. No auth (Chroma 1.x has none), so loopback only (R16) | Supervisor |
| Ollama | user-installed | `127.0.0.1:11434` | LLM inference | External. Health-checked only |
| OBS Studio | user-installed | `127.0.0.1:4455` | Recording | External. Capture worker can launch it with `--minimize-to-tray --profile Titan --collection Titan` |

**Start order:** Postgres, then Redis check, then Chroma, then Alembic migrate, then `titan-api`, then workers, then (on session start) `titan-telemetry`, `titan-capture`, `titan-orchestrator`. Ollama and OBS are checked by the first-run wizard and on session start. A missing Ollama blocks agent start with a clear UI error. A missing OBS blocks recording only.

### 2.4 Communication planes
| Plane | Transport | Used for | Guarantees |
|---|---|---|---|
| Control | REST over HTTP/1.1 JSON | UI commands, CRUD, session control | Request/response, idempotency keys on POSTs that create things |
| Realtime | Redis Streams into the WS gateway | Agent messages, telemetry, events, recording status, metrics | Ordered per stream. Replay from `seq`. At-least-once to persister |
| Jobs | Celery over Redis | Long or batch work | `acks_late=True`, `task_reject_on_worker_lost=True`, idempotent task design |
| Data | Postgres, Chroma, files under the session dir | Persistence | Postgres is the source of truth |
| Safety | Redis pub/sub `titan:safety:kill` **plus** direct Electron-to-actions named pipe `\\.\pipe\titan-safety` (P4) | Kill switch | Two independent paths. Delivery target under 50 ms |

### 2.5 Redis key and stream layout
All keys use the prefix `titan:`. `{sid}` is the session UUID.

| Key | Type | Producer to consumers | Retention |
|---|---|---|---|
| `titan:s:{sid}:bus` | Stream | orchestrator, API (user chat) to orchestrator, WS gateway, persister | `MAXLEN ~ 200000` |
| `titan:s:{sid}:telemetry` | Stream | telemetry host to orchestrator (world_state), WS gateway (downsampled) | `MAXLEN ~ 36000` (1 h at 10 Hz) |
| `titan:s:{sid}:events` | Stream | telemetry host, capture, orchestrator to everyone, persister | `MAXLEN ~ 100000` |
| `titan:s:{sid}:recording` | Stream | capture to WS gateway | `MAXLEN ~ 10000` |
| `titan:s:{sid}:bb:{section}` | Hash `key -> json{version,value,author,...}` | blackboard service | Session lifetime, then deleted |
| `titan:s:{sid}:bb:version` | String (INCR) | blackboard service | Global blackboard version counter |
| `titan:sys:metrics` | Stream | supervisor (1 Hz) | `MAXLEN ~ 3600` |
| `titan:safety:state` | Hash | actions, API | Persistent |
| `titan:safety:kill` | Pub/Sub channel | Electron (via API), actions | n/a |
| `titan:llm:usage:{yyyymmddhhmm}` | Hash | LLM Scheduler | TTL 2 h (tokens-per-minute gauge) |
| `titan:lock:session-live` | String, NX with TTL | API | Only one live session in v1 |

Consumer groups: `persist` (API), `ws` (one consumer per WebSocket connection uses `XREAD`, not a group), `orch` (orchestrator).

### 2.6 Live data flow and latency budget
```
Game --(kRPC stream / SCS shm @20Hz)--> titan-telemetry
   normalize (<=5ms) --> XADD telemetry (10Hz)          [budget: game->stream <= 50 ms]
   detect events     --> XADD events                     [<= 20 ms after frame]
        |                         |
        |                         +--> WS gateway --> UI event log         [<= 200 ms]
        v
 titan-orchestrator
   WorldStateUpdater: telemetry -> bb.world_state (1 Hz coalesced, events immediately)
   EventRouter: event -> subscribed agents' inboxes; salience >= 0.6 -> Floor Manager
   Floor Manager: pick speaker (<= 50 ms) -> LLM Scheduler priority P1 (commentary)
   LLM stream (Ollama) -> chat.delta envelopes -> bus --> WS --> Agents panel
                                       [event -> first token p50 <= 1.5 s, full <= 4 s]
   Director tick (every 15 s or on critical event) -> task.assign -> agents
```

### 2.7 Deployment on Windows
**Install layout** (per user; no admin rights except for the optional Memurai service install):
```
%LOCALAPPDATA%\Programs\Titan\            app binaries (Electron, resources\python, resources\pgsql, resources\ffmpeg)
%APPDATA%\Titan\config\titan.yaml         user config overrides
%LOCALAPPDATA%\Titan\data\pg\             Postgres cluster (initdb on first run, random password in Credential Manager)
%LOCALAPPDATA%\Titan\data\chroma\         Chroma persistence
%LOCALAPPDATA%\Titan\data\models\         sentence-transformers cache
%LOCALAPPDATA%\Titan\logs\<process>\      rotating JSON logs
<RecordingsRoot>\<yyyy-mm-dd>_<game>_<sid8>\  session dir (default %USERPROFILE%\Videos\Titan)
    session.json  telemetry\frames-0001.ndjson.zst  events.ndjson  messages.ndjson
    recording\gameplay.mkv  webcam.mkv  manifest.json
```
**Windows specifics:**
- Celery: never use prefork. Use `-P threads` for I/O and `-P solo` for GPU and media, so at most one GPU job runs at a time. Set `worker_prefetch_multiplier=1`.
- Process priority: Titan's Python processes run at `BELOW_NORMAL_PRIORITY_CLASS`, except `titan-actions` (`ABOVE_NORMAL`, P4) and `titan-telemetry` (`NORMAL`). The game is never changed.
- Ollama environment recommended by the wizard: `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_NUM_PARALLEL=2`, `OLLAMA_KEEP_ALIVE=30m`, `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`.
- Windows Defender exclusion for the recordings root is suggested (not forced) to avoid recording I/O stalls.
- Long paths: the installer enables `LongPathsEnabled` guidance. All code uses `pathlib` and never assumes `C:`.
- Firewall: every listener binds `127.0.0.1`, so Windows Firewall prompts never appear.

### 2.8 Storage choices
| Data | Store | Notes |
|---|---|---|
| Entities, logs, blackboard history, tasks, messages, events | PostgreSQL | Section 4 |
| Raw telemetry (10 to 20 Hz) | zstd NDJSON chunk files per session (rotated every 5 min) | Cheap writes, replayable. 1 Hz downsample goes to the `telemetry_samples` table |
| Semantic memory, knowledge, strategies, commentary history | Chroma | Index only. Every document has a Postgres row |
| Media | Files in the session dir. Postgres stores paths, checksums, durations | |
| Secrets | Windows Credential Manager through `keyring` (DPAPI) | Never in Postgres, config, or logs |
| LangGraph checkpoints | Postgres schema `lg` (`langgraph-checkpoint-postgres`) | |

### 2.9 Model-provider abstraction

#### 2.9.1 Interface (in `packages/py/titan-models`)
```python
class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str
    name: str | None = None
    tool_call_id: str | None = None

class ToolSpec(BaseModel):
    name: str; description: str; parameters: dict  # JSON Schema

class GenerationParams(BaseModel):
    temperature: float = 0.7; top_p: float = 0.9; max_tokens: int = 256
    stop: list[str] = []; seed: int | None = None
    json_schema: dict | None = None        # structured output (Ollama `format`)
    tools: list[ToolSpec] = []
    keep_alive: str | None = None

class ChatResult(BaseModel):
    text: str; tool_calls: list[dict]; model: str; provider: str
    prompt_tokens: int; completion_tokens: int; ttft_ms: int; latency_ms: int
    finish_reason: Literal["stop", "length", "tool", "error", "cancelled"]

class ModelCapabilities(BaseModel):
    context_tokens: int; supports_tools: bool; supports_json_schema: bool
    supports_vision: bool; est_vram_mb: int; device: Literal["gpu", "cpu", "mixed"]

class ModelProvider(Protocol):
    id: str                                         # "ollama", "openai_compat:lmstudio"
    async def list_models(self) -> list[str]: ...
    async def capabilities(self, model: str) -> ModelCapabilities: ...
    async def chat(self, model: str, messages: list[ChatMessage], params: GenerationParams,
                   cancel: asyncio.Event | None = None) -> ChatResult: ...
    def stream_chat(self, model: str, messages: list[ChatMessage], params: GenerationParams,
                    cancel: asyncio.Event | None = None) -> AsyncIterator[str | ChatResult]: ...
    async def embed(self, model: str, texts: list[str]) -> list[list[float]]: ...
    async def ensure_loaded(self, model: str) -> None: ...
    async def unload(self, model: str) -> None: ...
    async def health(self) -> bool: ...
```
Built-in implementations: `OllamaProvider` (native `/api/chat`, `/api/embed`, `/api/ps`; unload with `keep_alive: 0`), `OpenAICompatProvider` (`/v1/chat/completions`), `SentenceTransformersEmbedder` (in-process, CPU, implements `embed` only), and `FakeProvider` (deterministic scripted outputs for tests). Third-party providers register through the entry point group `titan.model_providers`. Cloud providers are **not** shipped. A user can add one only through an explicit plugin plus an `allow_cloud: true` setting.

#### 2.9.2 Role routing (`config/models.yaml`)
```yaml
profile: vram_12gb            # vram_8gb | vram_12gb | vram_16gb | vram_24gb | cpu_only
providers:
  ollama: { kind: ollama, base_url: "http://127.0.0.1:11434" }
  st:     { kind: sentence_transformers, device: cpu }
profiles:
  vram_12gb:
    roles:
      director:    { provider: ollama, model: "qwen3:8b",  params: { temperature: 0.3, max_tokens: 512 } }
      planner:     { provider: ollama, model: "qwen3:8b",  params: { temperature: 0.2 } }
      reasoning:   { provider: ollama, model: "qwen3:8b",  params: { temperature: 0.2 } }
      agent:       { provider: ollama, model: "qwen3:8b",  params: { temperature: 0.6, max_tokens: 200 } }
      commentary:  { provider: ollama, model: "qwen3:8b",  params: { temperature: 0.9, max_tokens: 80 } }
      summarizer:  { provider: ollama, model: "qwen3:8b",  params: { temperature: 0.2, max_tokens: 800 } }
      coder:       { provider: ollama, model: "qwen3:8b" }
      embedding:   { provider: st,     model: "BAAI/bge-small-en-v1.5" }
  vram_24gb:
    roles:
      director:    { provider: ollama, model: "qwen3:14b" }
      planner:     { provider: ollama, model: "deepseek-r1:14b" }
      commentary:  { provider: ollama, model: "llama3.1:8b" }
      coder:       { provider: ollama, model: "deepseek-coder-v2:16b" }
      # roles not listed inherit from vram_12gb
fallbacks:                    # tried in order when a model is missing, OOM, or timing out
  default: [ { provider: ollama, model: "qwen3:4b" }, { provider: ollama, model: "qwen3:1.7b", device: cpu } ]
```
Model tags are examples. The wizard lists `ollama list`, shows each tag's VRAM size, and pins the user's choices. The family-to-role mapping from the source (Qwen for reasoning, DeepSeek for planning and coding, Llama for storytelling) is the `vram_24gb` default. Smaller profiles collapse onto one model to avoid swapping (D9).

#### 2.9.3 LLM Scheduler (inside the orchestrator; Celery `llm_batch` uses the same client library with priority P4)
- Priority queue: **P0** safety and Director critical-event replans, **P1** live commentary, **P2** Director routine tick, **P3** agent deliberation, **P4** batch (summaries, consolidation).
- Concurrency equals `OLLAMA_NUM_PARALLEL` (default 2). One slot is reserved for P0/P1 whenever a session is live.
- Pre-emption: a P1 request arriving when both slots hold P3/P4 work cancels the oldest P3 request. Its agent gets `finish_reason=cancelled` and retries next tick.
- Deadlines: P1 requests older than 3 s before starting are dropped (stale commentary is worse than none).
- Token accounting goes to `llm_calls` and the per-minute Redis gauge. Soft budget: `max_tokens_per_minute` (default 12000) throttles P3 first.

#### 2.9.4 Resource Guard (GPU contention)
The supervisor publishes `fps_avg_5s`, `gpu_util`, `vram_used_mb`, and `vram_total_mb` at 1 Hz. The orchestrator records a **baseline FPS** during the first 60 s of a live session before agents start their LLM work (agents run in "listen-only" for that minute). Degradation ladder, applied in order with 30 s hysteresis:

| Level | Trigger | Action |
|---|---|---|
| L0 | Normal | none |
| L1 | FPS under 90% of baseline for 10 s, or VRAM free under 1.0 GB | Agent tick interval x2. Pause `titan-worker-gpu` |
| L2 | FPS under 80% of baseline for 10 s | Commentary only from the Floor Manager. Director tick 60 s. `max_tokens` halved |
| L3 | FPS under 70% of baseline, or VRAM free under 0.5 GB | Switch the role map to the fallback model (smaller, or CPU). Notify the user |
| L4 | User toggle "Game priority: max" | Unload the model. Agents idle. Telemetry and recording continue |

### 2.10 Game plugin and adapter interface

A game integration is a Python distribution in `games/<slug>/` registered under the entry point group `titan.games`. It contains a manifest, an adapter class, event rules, control defaults, team templates, and replay fixtures. **Core code never imports a game package by name.**

#### 2.10.1 Manifest (`titan-game.yaml`)
```yaml
id: ets2                                   # unique slug
name: Euro Truck Simulator 2
adapter: titan_game_scs.adapter:ScsAdapter  # import path
adapter_version: 1.0.0
domain: ground_vehicle                     # space | ground_vehicle | aircraft | naval | strategy | other
genre: [simulation, driving]
detection:
  steam_app_ids: [227300]
  epic_catalog_ids: []
  gog_product_ids: []
  executables: ["bin/win_x64/eurotrucks2.exe"]
  registry_keys: []
launch:
  steam_uri: "steam://rungameid/227300"
  args: []
telemetry:
  provider: scs_shared_memory              # implemented by the adapter
  requires_plugin: true
  plugin: { name: scs-sdk-plugin, version: "1.12.1", install_to: "bin/win_x64/plugins/scs-telemetry.dll", sha256: "<pinned>" }
  native_rate_hz: 20
capabilities:
  telemetry: true
  control: none                            # P1: none. P4: api | virtual_gamepad | keyboard_mouse
  anti_cheat: false                        # true => action layer permanently disabled for this game
  multiplayer_modes: ["convoy"]            # action layer refuses when a multiplayer mode is detected
config_files:
  - { path: "%USERPROFILE%/Documents/Euro Truck Simulator 2/profiles/*/controls.sii", kind: controls, parser: scs_sii }
save_files: ["%USERPROFILE%/Documents/Euro Truck Simulator 2/profiles/*/save/**"]
event_rules: events.yaml                   # declarative rules (Section 7.5)
teams: teams/                              # default team templates (Appendix A)
controls_default: controls_default.yaml
fixtures: fixtures/                        # recorded telemetry for replay tests
```

#### 2.10.2 Adapter interface (`packages/py/titan-sdk-games`)
```python
class GameAdapter(ABC):
    manifest: GameManifest

    # discovery and setup
    @classmethod
    def detect(cls, ctx: DiscoveryContext) -> list[DetectedInstall]: ...   # default impl uses manifest.detection
    def check_integration(self, profile: GameProfile) -> IntegrationStatus: ...  # plugin present? version ok?
    def install_integration(self, profile: GameProfile, consent: Consent) -> IntegrationStatus: ...
    def parse_controls(self, profile: GameProfile) -> list[ControlBindingDTO]: ...

    # runtime (called by titan-telemetry)
    async def connect(self, profile: GameProfile, cfg: AdapterConfig) -> None: ...
    async def disconnect(self) -> None: ...
    def frames(self) -> AsyncIterator[RawFrame]: ...          # native-rate raw frames
    def normalize(self, raw: RawFrame) -> TelemetryFrame: ... # Section 7.2 schema
    def detect_events(self, prev: TelemetryFrame | None, cur: TelemetryFrame,
                      raw: RawFrame) -> list[GameEventDTO]: ... # default impl runs event_rules
    def scene(self, frame: TelemetryFrame) -> str: ...        # "flight", "map", "driving", "menu", ...

    # context for agents
    def world_state_summary(self, frame: TelemetryFrame) -> dict: ...  # compact dict for prompts (<= 600 tokens)
    def default_team(self) -> TeamTemplate: ...
    def tools(self) -> list[AgentTool]: ...                   # read-only calculators, e.g. delta-v, ETA, fuel range

    # Phase 4 (raises NotSupported in P1)
    def action_space(self) -> ActionSpace: ...
    async def execute(self, action: ActionRequest) -> ActionResult: ...  # only titan-actions calls this
```
**How a new game is added without core changes:** create `games/<slug>/` with a manifest and an adapter subclass (often only `connect`, `frames`, and `normalize`). Add `events.yaml` and a team template. Record a fixture with `tools/record-fixture`. `pip install` it into the venv (or drop a wheel into `%APPDATA%\Titan\plugins\`, which is loaded only when the user toggles "trust" in Settings). Discovery, UI, recording, agents, and memory pick it up from the manifest. ETS2 and ATS share `games/scs-common` (one adapter class, two manifests).

**Discovery sources (Phase 1):** Steam (`HKCU\Software\Valve\Steam\SteamPath`, then `steamapps\libraryfolders.vdf`, then `appmanifest_<id>.acf` for install dir and `buildid`). Epic (`%PROGRAMDATA%\Epic\EpicGamesLauncher\Data\Manifests\*.item` JSON). GOG (`HKLM\SOFTWARE\WOW6432Node\GOG.com\Games\*`). Standalone (user picks an exe, matched against `detection.executables`). Ubisoft and EA are discovery stubs returning nothing in v1, behind the same `StoreScanner` interface.

### 2.11 Orchestration runtime (LangGraph)
- **SessionRuntime** (one per orchestrator process) owns: `Bus` (Redis Streams client), `Router` (in-process inboxes, one `asyncio.Queue` per agent instance, max 200, oldest non-task message dropped when full), `BlackboardService`, `FloorManager`, `LLMScheduler`, `MemoryService`, `WorldStateUpdater`, `DirectorRuntime`, and `AgentRuntime[]`.
- **AgentRuntime graph** (compiled `StateGraph`, `thread_id = agent_instance_id`):
  ```
  [wake] -> perceive -> decide --(no-op)--> sleep
                           |--(speak)--> request_floor -> (granted) -> speak -> reflect -> sleep
                           |--(task work)--> work(tool calls<=3) -> report -> reflect -> sleep
                           '--(bb update)--> write_bb -> sleep
  ```
  Wake triggers: inbox message, subscribed event, or tick timer (`agents.tick_interval_ms`, default 10 s, adjusted by Resource Guard). `perceive` builds the prompt context: persona system prompt, the agent's open tasks, blackboard slices (sections in `agents.subscriptions.bb_sections`, newest 30 entries), `world_state_summary`, the last 12 public chat lines, and the top 5 memories by retrieval (Section 4.3). Context is capped at 3,000 tokens by priority truncation. `decide` uses JSON-schema structured output: `{"intent": "none|speak|work|bb_write", ...}`.
- **Director graph** (`thread_id = session_id + ":director"`): `observe -> evaluate_tasks -> plan -> assign -> report`, ticking every 15 s, or immediately on events with `severity >= warning`, `task.fail`, or user chat addressed to the Director.
- Checkpointer: `AsyncPostgresSaver` (schema `lg`). On restart, the orchestrator rebuilds the Redis blackboard cache from `blackboard_current`, resumes graphs from their last checkpoint, and re-reads the bus from the last persisted `seq`.

### 2.12 Capture and recording
- `titan-capture` provisions (on first run, idempotently) an OBS profile `Titan` and scene collection `Titan` over obs-websocket. Scene `Titan Gameplay` contains a `game_capture` source (hook the adapter's executable) and audio inputs. **OBS recording settings:** MKV container, video encoder `jim_nvenc` (H.264) or `jim_hevc_nvenc` at CQP 18 to 22 (AMF or QSV equivalent), resolution and FPS from the session profile (1080p, 1440p, or 4K at 30, 60, or 120). Audio tracks: **1 game/system (desktop audio), 2 microphone, 3 agent voices (Application Audio Capture of `titan-voice` process, silent in P1), 4 music (P6)**. Audio encoder PCM or FLAC where the OBS version supports it, otherwise AAC 320 kbps (recorded in `manifest.json`).
- **Webcam:** FFmpeg owns the device: `-f dshow -video_size 1920x1080 -framerate 30 -i video="<cam>"`, `split` into (a) `h264_nvenc` CQ 20 into `webcam.mkv` and (b) 640x360 at 15 fps MJPEG served at `http://127.0.0.1:8767/webcam.mjpeg` for the UI. Face tracking in P1 is MediaPipe Face Detector (WASM) in the renderer on the preview stream: bounding box and "face present" only.
- **Sync:** at record start, capture notes `t_mono_ns` when OBS reports `OBS_WEBSOCKET_OUTPUT_STARTED` and when FFmpeg emits its first frame (parsed from `-progress`). Each track's `start_offset_ms` is relative to `recordings.start_mono_ns`. Events and markers map to the timeline with `t_ms = (event.t_mono_ns - recording.start_mono_ns) / 1e6`.
- On stop: OBS `StopRecord` and FFmpeg `q`, then a `media` job remuxes MKV to MP4 (stream copy), splits OBS audio tracks into separate files (`ffmpeg -map 0:a:N -c copy`), computes checksums, and finalizes `manifest.json` plus `recording_tracks` rows.
- Disk guard: refuse to start under 20 GB free. Warn at 10 minutes of remaining capacity based on the measured bitrate.

### 2.13 UI architecture and layout
Electron with `contextIsolation: true`, `sandbox: true`, `nodeIntegration: false`. Preload exposes `window.titan = { apiBase, token, platform, onKillSwitch(), onMenuCommand() }` (plus read-only `backend`, `killHotkey` and `versions` for the About dialog). The packaged renderer is served from the privileged `app://titan` scheme, not `file://` (Section 9.6). State is Redux Toolkit. Server data comes from RTK Query. Realtime data comes from one `WsClient` middleware that dispatches into slices (`chat`, `telemetry`, `events`, `recording`, `system`, `safety`). The telemetry slice keeps a ring buffer (600 frames) for Recharts sparklines.
```
+--------------------------------------------------------------------------------+
| FILE | EDIT | VIEW | AI | RECORD | TOOLS | HELP              [REC 00:12:31] [KILL] |
+--------------------------------------------------------------------------------+
|                                                                                |
|                         GAME WINDOW (desktopCapturer preview)                  |
|                         overlay: scene, mission, active event toasts           |
|                                                                                |
+-------------------------------------------+------------------------------------+
| AI AGENTS PANEL                           | WEBCAM PANEL                       |
|  [Director] [Flight Eng] [Planner] ...    |  MJPEG preview + face box          |
|  chat stream: avatar, name, role colour,  |  mic level meter (dBFS)            |
|  streaming text, event chips, @mentions   |  REC state per track, dropped fr.  |
|  input: "Message the crew..."  [Send]     |                                    |
+-------------------------------------------+------------------------------------+
| FPS 72 | CPU 38% | GPU 81% | VRAM 9.8/12G | RAM 21G | TOKENS 4.1k/m | GOALS 2 | TASKS 5 |
+--------------------------------------------------------------------------------+
| EVENT LOG (virtualized, filter by category/severity, click -> jump marker)        |
+--------------------------------------------------------------------------------+
```
Menus: **FILE** (New Session, Open Session, Replay Session, Settings, Exit). **EDIT** (Personas, Teams, Control Bindings). **VIEW** (toggle panels, Blackboard Inspector, Message Inspector, Telemetry Charts). **AI** (Start/Stop Agents, Models, Director Report, Memory Browser). **RECORD** (Start/Stop, Add Marker `Ctrl+M`, Recording Settings, Open Folder). **TOOLS** (Game Discovery, Integration Installer, Logs, Diagnostics bundle). **HELP** (Docs, About, Licenses).

---

## 3. Repository structure

A single monorepo with `pnpm` workspaces for TypeScript and `uv` workspaces for Python. Paths marked (P1) are created in Phase 1. The rest are stubs with a `README.md` until their phase.

```
titan/
|-- README.md                          Quick start, dev setup, links to spec
|-- LICENSE                            Apache-2.0 (open-source friendly; check deps for compatibility in M0)
|-- package.json                       pnpm root: scripts dev, build, lint, test, codegen
|-- pnpm-workspace.yaml                apps/*, packages/ts/*
|-- pyproject.toml                     uv workspace root, ruff/mypy/pytest config
|-- uv.lock                            Locked Python deps (committed)
|-- pnpm-lock.yaml                     Locked Node deps (committed)
|-- .python-version                    3.12
|-- .nvmrc                             22
|-- .editorconfig / .gitattributes     LF everywhere except *.bat/*.ps1; LFS rules for fixtures > 5 MB
|-- .gitignore                         data/, recordings, *.env, node_modules, .venv, dist
|-- .pre-commit-config.yaml            ruff, mypy (changed pkgs), eslint, prettier, codegen-check, gitleaks
|-- docker-compose.yml                 Dev/CI only: Postgres 16, Redis 7, Chroma on 127.0.0.1 (ADR 0020); never used by the app
|-- .github/
|   |-- workflows/ci.yml               Lint, type-check, unit, contract, integration (Linux), Windows jobs (Sec 9.3)
|   |-- workflows/release.yml          Tag -> Windows installer build -> draft GitHub Release
|   |-- workflows/codegen-check.yml    Fails if generated schemas/types differ from committed ones
|   |-- actions/setup/                 Composite action: Node/pnpm and uv with frozen lockfiles
|   |-- dependabot.yml                 Weekly pip (uv), npm and Actions updates
|   |-- PULL_REQUEST_TEMPLATE.md       Task ID, acceptance criteria checklist, ADR link, test evidence
|   `-- CODEOWNERS                     Protected paths: schemas/, packages/py/titan-core/protocol, services/actions
|-- docs/
|   |-- titan-architecture-spec.md     THIS DOCUMENT (source of truth)
|   |-- adr/0001-postgres-over-sqlite.md ... ADRs D1-D19 and later decisions
|   |-- dev-setup.md                   Windows dev machine setup (Ollama, OBS, Memurai, kRPC, SCS plugin)
|   |-- game-adapter-guide.md          How to add a game (Sec 2.10)
|   `-- runbooks/                      Recovery, diagnostics bundle, DB restore
|-- apps/
|   `-- desktop/                       (P1) Electron + React app
|       |-- package.json               electron, electron-vite, react, @mui/material, @reduxjs/toolkit, recharts
|       |-- electron.vite.config.ts    Build config for main/preload/renderer
|       |-- electron-builder.yml       NSIS installer; extraResources: python, pgsql, ffmpeg, config
|       |-- src/main/index.ts          App lifecycle, window, menus, spawns supervisor, launch token, app:// protocol
|       |-- src/main/menu.ts           FILE/EDIT/VIEW/AI/RECORD/TOOLS/HELP menu definition
|       |-- src/main/killSwitch.ts     globalShortcut Ctrl+Shift+F12 -> API /safety/kill + named pipe
|       |-- src/main/supervisor.ts     Spawn/monitor titan-supervisor, tree-kill on quit
|       |-- src/main/gamePreview.ts    desktopCapturer source lookup for game window
|       |-- src/preload/index.ts       contextBridge: window.titan {apiBase, token, platform, onKillSwitch, onMenuCommand}
|       |-- src/renderer/main.tsx      React root, theme, store provider
|       |-- src/renderer/app/store.ts  Redux store, RTK Query api, WS middleware
|       |-- src/renderer/app/ws.ts     WsClient: auth, subscribe, resume by seq, backoff
|       |-- src/renderer/features/operations/   Operations Center layout
|       |-- src/renderer/features/agents/       Agents panel, chat stream, persona chips
|       |-- src/renderer/features/webcam/       MJPEG preview, mic meter, face detector
|       |-- src/renderer/features/telemetry/    Telemetry bar, charts
|       |-- src/renderer/features/events/       Event log (virtualized)
|       |-- src/renderer/features/sessions/     New/open/replay session dialogs
|       |-- src/renderer/features/games/        Discovery, integration installer
|       |-- src/renderer/features/settings/     Models, recording, safety, paths
|       |-- src/renderer/features/inspectors/   Blackboard and message inspectors
|       `-- tests/e2e/                 Playwright-Electron tests against replay mode
|-- services/
|   |-- supervisor/titan_supervisor/   (P1) process manager, health, metrics (PresentMon, NVML, psutil)
|   |   |-- main.py                    Entry point; reads process table from config
|   |   |-- processes.py               Process specs, start order, restart policy
|   |   |-- postgres.py                initdb/pg_ctl wrapper for portable PG
|   |   `-- metrics.py                 1 Hz system metrics -> titan:sys:metrics
|   |-- api/titan_api/                 (P1) FastAPI app
|   |   |-- main.py                    App factory, routers, middleware, lifespan
|   |   |-- auth.py                    Launch-token bearer check (REST + WS first message)
|   |   |-- errors.py                  RFC 7807 problem+json handlers, error codes
|   |   |-- routers/                   One module per resource group (Sec 5.2)
|   |   |-- ws/gateway.py              Multiplexed WebSocket, channel registry, resume
|   |   |-- session_controller.py      Session state machine; asks supervisor to start session processes
|   |   `-- persister.py               Redis Streams -> Postgres batch writer (consumer group persist)
|   |-- orchestrator/titan_orchestrator/ (P1) multi-agent runtime
|   |   |-- main.py                    Entry: --session-id; builds SessionRuntime
|   |   |-- runtime.py                 SessionRuntime wiring (bus, router, services)
|   |   |-- router.py                  In-process inboxes, recipient resolution
|   |   |-- blackboard.py              BlackboardService (Sec 6.4)
|   |   |-- director/graph.py          Director LangGraph
|   |   |-- director/tasks.py          Task lifecycle state machine (Sec 6.5)
|   |   |-- agents/graph.py            Generic AgentRuntime LangGraph
|   |   |-- agents/context.py          Prompt context builder with token budget
|   |   |-- agents/tools.py            Tool registry (adapter tools + core tools)
|   |   |-- floor.py                   FloorManager commentary turn-taking (Sec 6.7)
|   |   |-- llm_scheduler.py           Priority scheduler (Sec 2.9.3)
|   |   |-- resource_guard.py          Degradation ladder (Sec 2.9.4)
|   |   |-- world_state.py             Telemetry -> bb.world_state
|   |   `-- session_end.py             End-of-session report and memory writes
|   |-- telemetry/titan_telemetry/     (P1) adapter host
|   |   |-- main.py                    Entry: --session-id --game-profile-id [--replay path]
|   |   |-- host.py                    Load adapter via entry point; frame loop; rate control
|   |   |-- rules.py                   Declarative event rule engine (Sec 7.5)
|   |   |-- writer.py                  zstd NDJSON chunk writer, 1 Hz Postgres sampler
|   |   `-- replay.py                  Replays fixture/session frames at 1x/2x/10x
|   |-- capture/titan_capture/         (P1) recording
|   |   |-- main.py                    Entry; command loop over Redis
|   |   |-- obs.py                     obs-websocket v5 client, profile/scene provisioning
|   |   |-- webcam.py                  FFmpeg dshow process, MJPEG preview server
|   |   |-- manifest.py                Recording manifest and track rows
|   |   `-- devices.py                 Enumerate cameras/mics (ffmpeg -list_devices)
|   |-- workers/titan_workers/         (P1) Celery
|   |   |-- celery_app.py              App, queues, routing, Windows pool settings
|   |   |-- tasks/memory.py            Embed, consolidate, reindex
|   |   |-- tasks/media.py             Remux, split tracks, checksums
|   |   |-- tasks/session.py           Session summary, lessons extraction
|   |   |-- tasks/research.py          (P2) research pipeline
|   |   |-- tasks/video.py             (P6) highlights, timeline, render
|   |   `-- tasks/publish.py           (P7) YouTube upload, analytics pull
|   `-- actions/titan_actions/         (P4) input gateway; P1 contains only the safety state client
|-- packages/
|   |-- py/titan-core/titan_core/      (P1) shared foundation
|   |   |-- config.py                  pydantic-settings layered config (Sec 9.5)
|   |   |-- logging.py                 structlog JSON setup, context vars
|   |   |-- ids.py                     UUIDv7
|   |   |-- clock.py                   Session monotonic clock helpers
|   |   |-- bus.py                     Redis Streams client (XADD/XREAD/groups, JSON codec)
|   |   |-- errors.py                  Error codes enum shared with API
|   |   |-- http.py                    Only allowed outbound HTTP client factory; enforces egress policy (Sec 9.7)
|   |   `-- protocol/                  Pydantic models: envelope, payloads, telemetry, ws, events (SOURCE OF TRUTH)
|   |-- py/titan-db/titan_db/          (P1) SQLAlchemy 2 models, repositories, session factory
|   |   |-- models/                    One module per aggregate (Sec 4.2)
|   |   |-- repositories/              Async repositories
|   |   `-- migrations/                Alembic env + versions
|   |-- py/titan-memory/titan_memory/  (P1) VectorStore interface, Chroma impl, embedder, retrieval scoring
|   |-- py/titan-models/titan_models/  (P1) ModelProvider protocol, Ollama, OpenAI-compat, ST, Fake
|   |-- py/titan-sdk-games/titan_sdk_games/ (P1) GameAdapter ABC, manifest model, discovery scanners, rule engine types, test harness
|   |-- py/titan-testing/titan_testing/ (P1) fixtures, fake bus, fake provider scripts, db fixtures
|   |-- ts/protocol/                   (P1) GENERATED TS types + zod validators from schemas/
|   `-- ts/ui-kit/                     (P1) shared MUI theme, AgentAvatar, Meter, StatusPill
|-- games/
|   |-- ksp/                           (P1) titan-game-ksp
|   |   |-- titan-game.yaml            Manifest
|   |   |-- titan_game_ksp/adapter.py  kRPC adapter
|   |   |-- titan_game_ksp/tools.py    Delta-v, TWR, orbit calculators (read-only)
|   |   |-- events.yaml                Event rules
|   |   |-- controls_default.yaml      Default KSP keybinds
|   |   |-- teams/default.yaml         Phase 1 team template
|   |   `-- fixtures/                  launch-to-orbit.ndjson.zst, crash.ndjson.zst
|   |-- scs-common/titan_game_scs/     (P1) shared SCS adapter, shm layout parser
|   |   `-- layouts/rencloud-1.12.yaml Versioned shared-memory layout
|   |-- ets2/                          (P1) manifest, events.yaml, teams, fixtures (uses scs-common)
|   `-- ats/                           (P1) manifest, events.yaml, teams, fixtures (uses scs-common)
|-- schemas/                           GENERATED JSON Schemas (envelope.json, payloads.json, telemetry.json, ws.json, events.json)
|-- config/
|   |-- titan.yaml                     Defaults: ports, paths, rates, feature flags
|   |-- models.yaml                    Role routing profiles (Sec 2.9.2)
|   |-- safety.yaml                    Rate limits, kill switch, policies (Sec 6.9)
|   |-- recording.yaml                 Recording presets
|   `-- personas/*.yaml                Built-in personas (Appendix A)
|-- third_party/
|   |-- manifest.yaml                  Pinned URLs + SHA-256 for PG, FFmpeg, PresentMon, SCS plugin, kRPC
|   `-- licenses/                      Third-party license texts
|-- installer/
|   |-- build-python.ps1               Embedded CPython + uv sync --frozen into resources/python
|   |-- build-pgsql.ps1                Stage portable PostgreSQL 16
|   `-- first-run/                     Wizard step definitions (Ollama, OBS, Memurai, plugins)
|-- tools/
|   |-- dev-up.ps1 / dev-up.sh         Start backing services + all processes for development
|   |-- codegen.py                     Pydantic -> JSON Schema -> TS types + zod
|   |-- fetch-third-party.py           Download and verify third_party/manifest.yaml entries
|   |-- record-fixture.py              Record adapter raw frames from a live game into a fixture
|   |-- diag-bundle.py                 Zip logs/config (secrets stripped) for bug reports
|   |-- lint-imports/                  import-linter contracts: service boundaries, input-library and raw-HTTP bans
|   `-- seed-dev-db.py                 Seed games, personas, teams
`-- tests/
    |-- integration/                   Cross-service tests (API + orchestrator + telemetry replay + fake LLM)
    |-- contract/                      Schemathesis on OpenAPI; WS message schema conformance
    |-- perf/                          Latency benchmarks (event -> first token, bus throughput)
    `-- hil/CHECKLIST.md               Hardware-in-the-loop manual checklist per milestone
```

---

## 4. Data model

### 4.1 Conventions
- PostgreSQL 16. One database `titan`, schema `public` for app tables, `lg` for LangGraph checkpoints.
- Primary keys `uuid` (UUIDv7 from the app). `created_at`/`updated_at timestamptz NOT NULL DEFAULT now()`, with `updated_at` kept current by a shared trigger `set_updated_at()`.
- Enums are `text` with `CHECK` constraints, so adding a value is a cheap migration.
- JSONB for flexible, game-specific data. Anything filtered or joined on goes in a real column.
- Migrations only through Alembic. Every migration has a downgrade. Destructive changes need an ADR.
- `t_session_ms` is milliseconds since `sessions.clock_origin_mono_ns`. `t_mono_ns` is raw `perf_counter_ns`.

### 4.2 DDL

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END; $$ LANGUAGE plpgsql;
-- Apply: CREATE TRIGGER trg_<table>_updated BEFORE UPDATE ON <table> FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ===================== Games =====================
CREATE TABLE games (
  id               uuid PRIMARY KEY,
  slug             text NOT NULL UNIQUE,                 -- 'ksp', 'ets2', 'ats'
  name             text NOT NULL,
  adapter_id       text NOT NULL,                        -- entry point name in titan.games
  adapter_version  text NOT NULL,
  domain           text NOT NULL CHECK (domain IN ('space','ground_vehicle','aircraft','naval','strategy','other')),
  genres           text[] NOT NULL DEFAULT '{}',
  capabilities     jsonb NOT NULL DEFAULT '{}',          -- {"telemetry":true,"control":"none","anti_cheat":false}
  store_ids        jsonb NOT NULL DEFAULT '{}',          -- {"steam":[227300]}
  research_status  text NOT NULL DEFAULT 'none' CHECK (research_status IN ('none','queued','running','complete','stale','failed')),
  manifest         jsonb NOT NULL,                       -- snapshot of titan-game.yaml
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE game_profiles (                            -- one detected installation
  id                 uuid PRIMARY KEY,
  game_id            uuid NOT NULL REFERENCES games(id) ON DELETE CASCADE,
  store              text NOT NULL CHECK (store IN ('steam','epic','gog','ubisoft','ea','standalone')),
  install_path       text NOT NULL,
  executable_path    text NOT NULL,
  launch_uri         text,                               -- steam://rungameid/227300
  launch_args        text[] NOT NULL DEFAULT '{}',
  game_version       text,                               -- Steam buildid or file version
  config_paths       jsonb NOT NULL DEFAULT '[]',
  save_paths         jsonb NOT NULL DEFAULT '[]',
  mod_paths          jsonb NOT NULL DEFAULT '[]',
  telemetry_status   text NOT NULL DEFAULT 'unknown' CHECK (telemetry_status IN ('unknown','missing','installed','connected','incompatible')),
  telemetry_details  jsonb NOT NULL DEFAULT '{}',        -- {"plugin":"scs-sdk-plugin","version":"1.12.1"}
  is_default         boolean NOT NULL DEFAULT false,
  last_seen_at       timestamptz,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (game_id, install_path)
);
CREATE UNIQUE INDEX ux_game_profiles_default ON game_profiles(game_id) WHERE is_default;

-- ===================== Agents =====================
CREATE TABLE agent_personas (
  id                      uuid PRIMARY KEY,
  slug                    text NOT NULL UNIQUE,          -- 'ksp.flight_engineer.gene'
  display_name            text NOT NULL,                 -- 'Gene'
  role                    text NOT NULL,                 -- 'flight_engineer'
  department              text NOT NULL CHECK (department IN ('director','research','agent_factory','training','gameplay','commentary','recording','video','seo','publish')),
  personality             jsonb NOT NULL,                -- {"traits":["dry","precise"],"humor":0.3,"verbosity":0.4,"catchphrases":[],"avoid":[]}
  backstory               text,
  speaking_style          text,
  system_prompt_template  text NOT NULL,                 -- Jinja2; vars: persona, game, mission, role_brief
  voice                   jsonb,                         -- (P5) {"engine":"xtts","voice_id":"...","rate":1.0}
  portrait_path           text,                          -- (P5) generated portrait
  color_hex               char(7) NOT NULL DEFAULT '#888888',
  model_role              text NOT NULL DEFAULT 'agent', -- key into models.yaml roles
  game_id                 uuid REFERENCES games(id) ON DELETE SET NULL, -- NULL = universal
  source                  text NOT NULL CHECK (source IN ('builtin','user','factory')),
  version                 int NOT NULL DEFAULT 1,
  created_at              timestamptz NOT NULL DEFAULT now(),
  updated_at              timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE agent_teams (
  id             uuid PRIMARY KEY,
  game_id        uuid REFERENCES games(id) ON DELETE CASCADE,  -- NULL = universal team
  name           text NOT NULL,
  purpose        text NOT NULL,
  template_slug  text,                                 -- 'ksp.default'
  source         text NOT NULL CHECK (source IN ('builtin','user','factory')),
  version        int NOT NULL DEFAULT 1,
  is_active      boolean NOT NULL DEFAULT true,
  created_at     timestamptz NOT NULL DEFAULT now(),
  updated_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (game_id, name, version)
);

CREATE TABLE agents (                                  -- durable agent definition (role within a team)
  id                 uuid PRIMARY KEY,
  team_id            uuid NOT NULL REFERENCES agent_teams(id) ON DELETE CASCADE,
  persona_id         uuid NOT NULL REFERENCES agent_personas(id),
  role               text NOT NULL,
  is_director        boolean NOT NULL DEFAULT false,
  responsibilities   text[] NOT NULL DEFAULT '{}',
  tools              text[] NOT NULL DEFAULT '{}',     -- allowlisted tool ids
  bb_read_sections   text[] NOT NULL DEFAULT '{goals,plan,world_state,facts,risks}',
  bb_write_sections  text[] NOT NULL DEFAULT '{facts,hypotheses,risks,discoveries}',
  event_subscriptions text[] NOT NULL DEFAULT '{}',    -- glob patterns: 'ksp.staging', 'scs.job.*'
  tick_interval_ms   int NOT NULL DEFAULT 10000 CHECK (tick_interval_ms >= 2000),
  can_commentate     boolean NOT NULL DEFAULT true,
  can_act            boolean NOT NULL DEFAULT false,   -- must be false in P1 (enforced by CHECK below in P1 migration)
  status             text NOT NULL DEFAULT 'active' CHECK (status IN ('active','probation','retired')),
  stats              jsonb NOT NULL DEFAULT '{}',      -- rolling: tasks_ok, tasks_failed, avg_eval, utterances
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (team_id, role),
  CONSTRAINT p1_no_actions CHECK (can_act = false)     -- dropped by the Phase 4 migration
);
CREATE UNIQUE INDEX ux_agents_one_director ON agents(team_id) WHERE is_director;

-- ===================== Sessions, missions, tasks =====================
CREATE TABLE sessions (
  id                    uuid PRIMARY KEY,
  game_id               uuid NOT NULL REFERENCES games(id),
  game_profile_id       uuid REFERENCES game_profiles(id) ON DELETE SET NULL,
  team_id               uuid REFERENCES agent_teams(id) ON DELETE SET NULL,
  title                 text,
  mode                  text NOT NULL DEFAULT 'observe' CHECK (mode IN ('observe','assist','autonomous','replay')),
  state                 text NOT NULL DEFAULT 'created' CHECK (state IN ('created','starting','live','paused','stopping','ended','failed')),
  replay_of_session_id  uuid REFERENCES sessions(id),
  clock_origin_mono_ns  bigint,
  clock_origin_wall     timestamptz,
  started_at            timestamptz,
  ended_at              timestamptz,
  data_dir              text NOT NULL,
  game_version          text,
  settings              jsonb NOT NULL DEFAULT '{}',   -- recording preset, agent toggles, model profile
  outcome               text CHECK (outcome IN ('success','partial','failure','aborted')),
  summary               jsonb,                          -- end-of-session report (Sec 6.10)
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_sessions_game_started ON sessions(game_id, started_at DESC);
CREATE UNIQUE INDEX ux_sessions_one_live ON sessions((true)) WHERE state IN ('starting','live','paused','stopping') AND mode <> 'replay';

CREATE TABLE missions (
  id                 uuid PRIMARY KEY,
  session_id         uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  game_id            uuid NOT NULL REFERENCES games(id),
  parent_mission_id  uuid REFERENCES missions(id) ON DELETE CASCADE,
  title              text NOT NULL,
  objective          text NOT NULL,
  success_criteria   jsonb NOT NULL DEFAULT '[]',      -- predicates over telemetry (Sec 7.5 DSL)
  failure_criteria   jsonb NOT NULL DEFAULT '[]',
  status             text NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','active','succeeded','failed','abandoned')),
  priority           smallint NOT NULL DEFAULT 5 CHECK (priority BETWEEN 0 AND 9),
  created_by         text NOT NULL,                     -- 'user' | 'director' | 'agent:<instance_id>'
  started_at         timestamptz,
  ended_at           timestamptz,
  result             jsonb,
  created_at         timestamptz NOT NULL DEFAULT now(),
  updated_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_missions_session ON missions(session_id, status);

CREATE TABLE agent_instances (                         -- runtime spawn of an agent within a session
  id                  uuid PRIMARY KEY,
  agent_id            uuid NOT NULL REFERENCES agents(id),
  session_id          uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  state               text NOT NULL CHECK (state IN ('spawning','ready','busy','paused','terminating','terminated','crashed')),
  spawned_by          text NOT NULL,                    -- 'session_start' | 'director' | 'user'
  spawned_at          timestamptz NOT NULL DEFAULT now(),
  terminated_at       timestamptz,
  termination_reason  text,
  model_resolved      text,                             -- 'ollama:qwen3:8b'
  lg_thread_id        text NOT NULL,
  tokens_in           bigint NOT NULL DEFAULT 0,
  tokens_out          bigint NOT NULL DEFAULT 0,
  messages_sent       int NOT NULL DEFAULT 0,
  last_heartbeat_at   timestamptz
);
CREATE INDEX ix_agent_instances_session ON agent_instances(session_id, state);

CREATE TABLE tasks (                                   -- Director-managed work items (Sec 6.5)
  id                     uuid PRIMARY KEY,
  session_id             uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  mission_id             uuid REFERENCES missions(id) ON DELETE SET NULL,
  parent_task_id         uuid REFERENCES tasks(id) ON DELETE CASCADE,
  kind                   text NOT NULL,                 -- 'analyze','plan','monitor','explain','compute','summarize'
  title                  text NOT NULL,
  input                  jsonb NOT NULL DEFAULT '{}',
  output                 jsonb,
  assignee_role          text,
  assignee_instance_id   uuid REFERENCES agent_instances(id) ON DELETE SET NULL,
  state                  text NOT NULL DEFAULT 'proposed' CHECK (state IN ('proposed','assigned','accepted','in_progress','blocked','completed','failed','cancelled','timed_out')),
  priority               smallint NOT NULL DEFAULT 5 CHECK (priority BETWEEN 0 AND 9),
  attempts               smallint NOT NULL DEFAULT 0,
  max_attempts           smallint NOT NULL DEFAULT 2,
  deadline_at            timestamptz,
  assigned_at            timestamptz,
  accepted_at            timestamptz,
  completed_at           timestamptz,
  failure_reason         text,
  evaluation             jsonb,                         -- {"score":0.0-1.0,"notes":"...","by":"director"}
  created_at             timestamptz NOT NULL DEFAULT now(),
  updated_at             timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_tasks_session_state ON tasks(session_id, state);
CREATE INDEX ix_tasks_assignee ON tasks(assignee_instance_id) WHERE state IN ('assigned','accepted','in_progress','blocked');

-- ===================== Knowledge, strategy, risk, controls =====================
CREATE TABLE research_sources (                        -- (P2, created in P1)
  id            uuid PRIMARY KEY,
  game_id       uuid NOT NULL REFERENCES games(id) ON DELETE CASCADE,
  kind          text NOT NULL CHECK (kind IN ('official_docs','wiki','forum','reddit','steam_guide','patch_notes','video','dev_blog','mod_docs','local_file','user')),
  url           text,
  local_path    text,
  title         text,
  fetched_at    timestamptz,
  http_status   int,
  content_hash  char(64),
  robots_allowed boolean,
  license_note  text,
  raw_path      text,
  created_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (game_id, url)
);

CREATE TABLE knowledge_entries (
  id            uuid PRIMARY KEY,
  game_id       uuid NOT NULL REFERENCES games(id) ON DELETE CASCADE,
  kind          text NOT NULL CHECK (kind IN ('mechanic','objective','economy','combat','progression','tech_tree','crafting','exploration','control','ui','vehicle','location','glossary','other')),
  title         text NOT NULL,
  body          text NOT NULL,
  structured    jsonb NOT NULL DEFAULT '{}',
  source_id     uuid REFERENCES research_sources(id) ON DELETE SET NULL,
  game_version  text,
  confidence    real NOT NULL DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
  verified      boolean NOT NULL DEFAULT false,
  content_hash  char(64) NOT NULL,
  chroma_id     text,                                    -- = id::text in collection 'knowledge'
  tsv           tsvector GENERATED ALWAYS AS (to_tsvector('english', title || ' ' || body)) STORED,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  UNIQUE (game_id, content_hash)
);
CREATE INDEX ix_knowledge_tsv ON knowledge_entries USING gin(tsv);
CREATE INDEX ix_knowledge_game_kind ON knowledge_entries(game_id, kind);

CREATE TABLE strategies (
  id                  uuid PRIMARY KEY,
  game_id             uuid NOT NULL REFERENCES games(id) ON DELETE CASCADE,
  title               text NOT NULL,
  level               text NOT NULL CHECK (level IN ('beginner','advanced','endgame','common_mistake','workflow')),
  situation           text NOT NULL,                     -- when it applies
  steps               jsonb NOT NULL DEFAULT '[]',
  rationale           text,
  source_kind         text NOT NULL CHECK (source_kind IN ('research','learned','user','builtin')),
  source_refs         jsonb NOT NULL DEFAULT '[]',       -- [{"type":"session","id":...},{"type":"source","id":...}]
  confidence          real NOT NULL DEFAULT 0.5 CHECK (confidence BETWEEN 0 AND 1),
  times_used          int NOT NULL DEFAULT 0,
  times_succeeded     int NOT NULL DEFAULT 0,
  status              text NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate','active','deprecated')),
  superseded_by       uuid REFERENCES strategies(id),
  game_version_range  text,
  chroma_id           text,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_strategies_game_status ON strategies(game_id, status, level);

CREATE TABLE risk_entries (
  id                  uuid PRIMARY KEY,
  game_id             uuid NOT NULL REFERENCES games(id) ON DELETE CASCADE,
  title               text NOT NULL,                     -- 'Fuel starvation during ascent'
  description         text NOT NULL,
  category            text NOT NULL CHECK (category IN ('crash','overheat','fuel','structural','economy','traffic_law','fatigue','mission_fail','other')),
  trigger_conditions  jsonb NOT NULL DEFAULT '[]',       -- predicate DSL (Sec 7.5)
  severity            smallint NOT NULL CHECK (severity BETWEEN 1 AND 5),
  likelihood          smallint NOT NULL CHECK (likelihood BETWEEN 1 AND 5),
  mitigation          text,
  event_type          text,                              -- event emitted when trigger fires
  source_kind         text NOT NULL CHECK (source_kind IN ('research','learned','user','builtin')),
  source_refs         jsonb NOT NULL DEFAULT '[]',
  occurrences         int NOT NULL DEFAULT 0,
  last_occurred_at    timestamptz,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_risks_game ON risk_entries(game_id, category);

CREATE TABLE control_bindings (
  id               uuid PRIMARY KEY,
  game_id          uuid NOT NULL REFERENCES games(id) ON DELETE CASCADE,
  game_profile_id  uuid REFERENCES game_profiles(id) ON DELETE CASCADE,   -- NULL = game default
  action_id        text NOT NULL,                      -- canonical: 'ksp.stage', 'vehicle.throttle'
  action_label     text NOT NULL,
  context          text NOT NULL DEFAULT 'default',    -- 'flight','map','eva','driving','menu'
  device           text NOT NULL CHECK (device IN ('keyboard','mouse','gamepad','joystick','hotas','wheel','api')),
  binding          jsonb NOT NULL,                      -- {"key":"Space","mods":[]} | {"axis":"LT","invert":false}
  action_class     text NOT NULL CHECK (action_class IN ('continuous','discrete','irreversible','menu')),
  source           text NOT NULL CHECK (source IN ('default','config_file','research','user')),
  confidence       real NOT NULL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT (game_id, game_profile_id, action_id, context, device)
);

-- ===================== Memory =====================
CREATE TABLE memories (
  id                uuid PRIMARY KEY,
  game_id           uuid REFERENCES games(id) ON DELETE CASCADE,
  agent_id          uuid REFERENCES agents(id) ON DELETE SET NULL,       -- NULL = team/shared memory
  session_id        uuid REFERENCES sessions(id) ON DELETE SET NULL,
  mission_id        uuid REFERENCES missions(id) ON DELETE SET NULL,
  tier              text NOT NULL CHECK (tier IN ('short_term','long_term','episodic','strategic','failure')),
  kind              text NOT NULL CHECK (kind IN ('observation','discovery','lesson','success','failure','summary','reflection','callback')),
  content           text NOT NULL,                     -- natural-language memory (<= 1000 chars)
  structured        jsonb NOT NULL DEFAULT '{}',
  importance        real NOT NULL DEFAULT 0.5 CHECK (importance BETWEEN 0 AND 1),
  confidence        real NOT NULL DEFAULT 0.7 CHECK (confidence BETWEEN 0 AND 1),
  t_session_ms      bigint,
  occurred_at       timestamptz NOT NULL DEFAULT now(),
  access_count      int NOT NULL DEFAULT 0,
  last_accessed_at  timestamptz,
  expires_at        timestamptz,                       -- short_term: session end + 24h
  supersedes        uuid REFERENCES memories(id),
  chroma_id         text,
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_memories_game_tier ON memories(game_id, tier, importance DESC);
CREATE INDEX ix_memories_session ON memories(session_id);
CREATE INDEX ix_memories_expiry ON memories(expires_at) WHERE expires_at IS NOT NULL;

-- ===================== Blackboard, events, messages, telemetry =====================
CREATE TABLE blackboard_entries (                       -- append-only history; current = max(version) per key
  id           uuid PRIMARY KEY,
  session_id   uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  section      text NOT NULL CHECK (section IN ('goals','plan','tasks','world_state','facts','hypotheses','risks','discoveries','lessons','notes')),
  key          text NOT NULL CHECK (key ~ '^[a-z0-9_.:-]{1,128}$'),
  version      int NOT NULL CHECK (version >= 1),
  op           text NOT NULL CHECK (op IN ('put','retract')),
  value        jsonb,
  author       text NOT NULL,                          -- 'agent:<instance_id>' | 'director' | 'system' | 'user'
  confidence   real CHECK (confidence BETWEEN 0 AND 1),
  evidence     jsonb NOT NULL DEFAULT '[]',            -- [{"type":"event","id":...},{"type":"telemetry","t_session_ms":...}]
  message_id   uuid,                                    -- envelope that caused this write
  bb_version   bigint NOT NULL,                         -- global blackboard counter at write
  expires_at   timestamptz,
  created_at   timestamptz NOT NULL DEFAULT now(),
  UNIQUE (session_id, section, key, version)
);
CREATE INDEX ix_bb_session_version ON blackboard_entries(session_id, bb_version);
CREATE VIEW blackboard_current AS
  SELECT DISTINCT ON (session_id, section, key) *
  FROM blackboard_entries
  ORDER BY session_id, section, key, version DESC;

CREATE TABLE events (
  id            uuid PRIMARY KEY,
  session_id    uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  seq           bigint NOT NULL,                        -- per-session monotonically increasing
  type          text NOT NULL,                          -- 'ksp.staging', 'scs.job.delivered', 'recording.started'
  category      text NOT NULL CHECK (category IN ('game','agent','system','user','safety','recording')),
  severity      text NOT NULL CHECK (severity IN ('debug','info','notice','warning','critical')),
  salience      real NOT NULL DEFAULT 0.3 CHECK (salience BETWEEN 0 AND 1),
  source        text NOT NULL,                          -- 'adapter:ksp', 'rule:ksp.max_q', 'capture'
  t_mono_ns     bigint NOT NULL,
  t_session_ms  bigint NOT NULL,
  occurred_at   timestamptz NOT NULL,
  payload       jsonb NOT NULL DEFAULT '{}',
  frame_seq     bigint,                                 -- telemetry frame that triggered it
  UNIQUE (session_id, seq)
);
CREATE INDEX ix_events_session_time ON events(session_id, t_session_ms);
CREATE INDEX ix_events_session_type ON events(session_id, type);

CREATE TABLE agent_messages (                          -- persisted bus envelopes
  id              uuid PRIMARY KEY,                     -- = envelope.id
  session_id      uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  stream_seq      text NOT NULL,                        -- Redis stream id
  type            text NOT NULL,
  sender          text NOT NULL,
  recipients      text[] NOT NULL,
  correlation_id  uuid,
  causation_id    uuid,
  visibility      text NOT NULL CHECK (visibility IN ('public','internal')),
  payload         jsonb NOT NULL,
  t_session_ms    bigint NOT NULL,
  created_at      timestamptz NOT NULL
);
CREATE INDEX ix_msgs_session_time ON agent_messages(session_id, t_session_ms);
CREATE INDEX ix_msgs_correlation ON agent_messages(correlation_id);

CREATE TABLE telemetry_samples (                       -- 1 Hz downsample; raw frames in session files
  session_id    uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  t_session_ms  bigint NOT NULL,
  frame         jsonb NOT NULL,                         -- normalized TelemetryFrame
  PRIMARY KEY (session_id, t_session_ms)
);

CREATE TABLE llm_calls (
  id                 uuid PRIMARY KEY,
  session_id         uuid REFERENCES sessions(id) ON DELETE SET NULL,
  agent_instance_id  uuid REFERENCES agent_instances(id) ON DELETE SET NULL,
  provider           text NOT NULL,
  model              text NOT NULL,
  model_role         text NOT NULL,
  purpose            text NOT NULL,                     -- 'commentary','decide','director_plan','summary'
  priority           smallint NOT NULL,
  prompt_tokens      int NOT NULL DEFAULT 0,
  completion_tokens  int NOT NULL DEFAULT 0,
  ttft_ms            int,
  latency_ms         int,
  status             text NOT NULL CHECK (status IN ('ok','error','cancelled','timeout','dropped')),
  error              text,
  prompt_hash        char(64),
  prompt_path        text,                              -- only if logging.llm_prompts=true
  created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_llm_calls_session ON llm_calls(session_id, created_at);

-- ===================== Recording =====================
CREATE TABLE recordings (
  id              uuid PRIMARY KEY,
  session_id      uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  state           text NOT NULL CHECK (state IN ('starting','recording','stopping','finalizing','complete','error')),
  preset          jsonb NOT NULL,                       -- {"width":1920,"height":1080,"fps":60,"encoder":"jim_nvenc","cq":20}
  start_mono_ns   bigint,
  started_at      timestamptz,
  stopped_at      timestamptz,
  duration_ms     bigint,
  root_dir        text NOT NULL,
  manifest_path   text,
  total_bytes     bigint NOT NULL DEFAULT 0,
  error           text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_recordings_session ON recordings(session_id);

CREATE TABLE recording_tracks (
  id               uuid PRIMARY KEY,
  recording_id     uuid NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  track_no         smallint NOT NULL,                   -- editor track number (Sec 2.12, P6 tracks 1-8)
  kind             text NOT NULL CHECK (kind IN ('gameplay_video','webcam_video','game_audio','mic_audio','agent_voice','user_commentary','music','system_audio','effects','overlay','captions','telemetry','events')),
  file_path        text NOT NULL,
  container        text,
  codec            text,
  width            int, height int, fps numeric(6,3),
  sample_rate      int, channels smallint,
  start_offset_ms  int NOT NULL DEFAULT 0,              -- relative to recordings.start_mono_ns
  duration_ms      bigint,
  bytes            bigint,
  sha256           char(64),
  dropped_frames   int NOT NULL DEFAULT 0,
  state            text NOT NULL CHECK (state IN ('recording','finalized','corrupt','missing')),
  created_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (recording_id, kind, track_no)
);

CREATE TABLE markers (                                 -- highlight candidates and user markers
  id            uuid PRIMARY KEY,
  session_id    uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  recording_id  uuid REFERENCES recordings(id) ON DELETE CASCADE,
  event_id      uuid REFERENCES events(id) ON DELETE SET NULL,
  t_ms          bigint NOT NULL,                        -- recording timeline ms
  duration_ms   int NOT NULL DEFAULT 0,
  kind          text NOT NULL CHECK (kind IN ('highlight','achievement','failure','funny','tension','emotional','mission_complete','chapter','user')),
  score         real NOT NULL DEFAULT 0.5 CHECK (score BETWEEN 0 AND 1),
  label         text,
  created_by    text NOT NULL,                          -- 'rule','agent:<id>','user','highlight_model'
  created_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_markers_recording ON markers(recording_id, t_ms);

-- ===================== Video, thumbnails, publishing, analytics (P6-P8; created in P1) =====================
CREATE TABLE video_projects (
  id                uuid PRIMARY KEY,
  session_id        uuid REFERENCES sessions(id) ON DELETE SET NULL,
  title             text NOT NULL,
  status            text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','rough_cut','editing','rendering','rendered','published','archived','failed')),
  timeline_path     text,                               -- OpenTimelineIO .otio
  timeline_version  int NOT NULL DEFAULT 0,
  render_profile    jsonb NOT NULL DEFAULT '{}',
  output_path       text,
  duration_ms       bigint,
  chapters          jsonb NOT NULL DEFAULT '[]',        -- [{"t_ms":0,"title":"Intro"}]
  captions_path     text,
  seo               jsonb NOT NULL DEFAULT '{}',        -- {"title","description","tags":[],"hashtags":[],"pinned_comment"}
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE video_project_sources (
  video_project_id  uuid NOT NULL REFERENCES video_projects(id) ON DELETE CASCADE,
  recording_id      uuid NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
  PRIMARY KEY (video_project_id, recording_id)
);

CREATE TABLE thumbnails (
  id                uuid PRIMARY KEY,
  video_project_id  uuid NOT NULL REFERENCES video_projects(id) ON DELETE CASCADE,
  style             text NOT NULL CHECK (style IN ('mrbeast','documentary','gaming','educational','simulation','humorous','professional')),
  source_marker_id  uuid REFERENCES markers(id) ON DELETE SET NULL,
  prompt            text,
  generator         jsonb NOT NULL DEFAULT '{}',        -- {"engine":"comfyui","workflow":"...","model":"flux-dev","seed":123}
  image_path        text NOT NULL,
  width             int NOT NULL, height int NOT NULL,
  score             real,                               -- predicted appeal 0-1
  selected          boolean NOT NULL DEFAULT false,
  ctr               real,                               -- observed (P8)
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_thumbnails_selected ON thumbnails(video_project_id) WHERE selected;

CREATE TABLE platform_accounts (
  id                 uuid PRIMARY KEY,
  platform           text NOT NULL CHECK (platform IN ('youtube','twitch','tiktok','kick','x','facebook')),
  display_name       text NOT NULL,
  remote_channel_id  text NOT NULL,
  scopes             text[] NOT NULL DEFAULT '{}',
  credential_ref     text NOT NULL,                     -- keyring service/key; token never stored here
  status             text NOT NULL CHECK (status IN ('connected','expired','revoked')),
  connected_at       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (platform, remote_channel_id)
);

CREATE TABLE upload_jobs (
  id                    uuid PRIMARY KEY,
  video_project_id      uuid NOT NULL REFERENCES video_projects(id) ON DELETE CASCADE,
  account_id            uuid NOT NULL REFERENCES platform_accounts(id),
  platform              text NOT NULL,
  status                text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','awaiting_approval','approved','uploading','processing','scheduled','published','failed','cancelled')),
  privacy               text NOT NULL DEFAULT 'private' CHECK (privacy IN ('private','unlisted','public')),
  scheduled_publish_at  timestamptz,
  metadata              jsonb NOT NULL,                 -- final title/description/tags/category/chapters/thumbnail_id
  approved_by           text,                           -- must be 'user'; API refuses otherwise
  approved_at           timestamptz,
  upload_session_uri    text,                           -- resumable upload URI
  bytes_sent            bigint NOT NULL DEFAULT 0,
  bytes_total           bigint,
  remote_video_id       text,
  remote_url            text,
  attempts              smallint NOT NULL DEFAULT 0,
  last_error            text,
  quota_units_used      int NOT NULL DEFAULT 0,
  created_at            timestamptz NOT NULL DEFAULT now(),
  updated_at            timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT approval_required CHECK (status NOT IN ('approved','uploading','processing','scheduled','published') OR approved_at IS NOT NULL)
);
CREATE INDEX ix_upload_jobs_status ON upload_jobs(status);

CREATE TABLE analytics_snapshots (
  id                  uuid PRIMARY KEY,
  upload_job_id       uuid NOT NULL REFERENCES upload_jobs(id) ON DELETE CASCADE,
  remote_video_id     text NOT NULL,
  captured_at         timestamptz NOT NULL,
  time_window         text NOT NULL CHECK (time_window IN ('1h','24h','7d','28d','lifetime')),
  views               bigint, impressions bigint,
  ctr                 numeric(6,4),
  watch_time_minutes  numeric(12,2),
  avg_view_duration_s numeric(10,2),
  avg_view_pct        numeric(6,3),
  likes int, comments int, shares int,
  subscribers_gained int, subscribers_lost int,
  retention_curve     jsonb,                            -- [[pct_of_video, audience_ratio], ...]
  raw                 jsonb NOT NULL DEFAULT '{}',
  UNIQUE (upload_job_id, time_window, captured_at)
);

CREATE TABLE settings (
  key         text PRIMARY KEY,                         -- 'ui.layout', 'safety.kill_hotkey'
  value       jsonb NOT NULL,
  updated_at  timestamptz NOT NULL DEFAULT now()
);
```

**Retention jobs** (`maintenance` beat task, daily): delete `memories` past `expires_at`. Keep `telemetry_samples` and `agent_messages` for 180 days by default (configurable). `events`, `blackboard_entries`, and summaries are kept indefinitely because Phase 8 uses them.

### 4.3 ChromaDB collections
One Chroma tenant `titan`, database `default`. Distance is `cosine` (`metadata={"hnsw:space":"cosine"}`). Every collection's metadata records `embedding_model`, `embedding_dim`, and `schema_version`. On mismatch, `titan memory reindex` rebuilds the collection from Postgres. Document ID equals the Postgres row `id` (text). Metadata values must be scalars, so lists are stored as `|`-joined strings.

| Collection | Source table | Document text | Metadata keys |
|---|---|---|---|
| `knowledge` | `knowledge_entries` (chunked 400 to 600 tokens, overlap 60; chunk id `<id>#<n>`) | title + chunk | `entry_id`, `game_id`, `kind`, `source_kind`, `game_version`, `confidence`, `verified` (bool), `created_ts` (int epoch) |
| `memories` | `memories` | content | `memory_id`, `game_id`, `agent_id` (or `""`), `role`, `session_id`, `tier`, `kind`, `importance`, `confidence`, `occurred_ts`, `mission_id` |
| `strategies` | `strategies` | title + situation + steps summary | `strategy_id`, `game_id`, `level`, `status`, `confidence`, `success_rate` |
| `risks` | `risk_entries` | title + description + mitigation | `risk_id`, `game_id`, `category`, `severity`, `likelihood` |
| `commentary` | public `chat.say` utterances | utterance text | `message_id`, `session_id`, `game_id`, `persona_slug`, `event_type`, `t_session_ms`, `created_ts` |

**Retrieval scoring** (in `titan-memory`): `score = 0.6*similarity + 0.2*importance + 0.1*recency + 0.1*confidence`, where `recency = exp(-age_days/30)`. Filter by `game_id` always, plus `agent_id in (self, "")` for memories. Return the top-k (default 5) and increment `access_count`. The `commentary` collection is queried with the candidate utterance before it is emitted: similarity over 0.92 against the last 50 session utterances triggers one regeneration with a "do not repeat" hint (Section 6.7).

---

## 5. API contracts

### 5.1 Conventions
- Base URL `http://127.0.0.1:8765/api/v1`. JSON UTF-8. Field names are `snake_case`. Timestamps are RFC 3339 UTC. IDs are UUID strings.
- **Auth:** `Authorization: Bearer <launch_token>`. The token is a 32-byte random value generated by Electron main at each launch and passed to the supervisor through an environment variable. Requests without it get `401`. `GET /health` is the only unauthenticated route.
- **Idempotency:** POSTs that create resources accept `Idempotency-Key` (UUID). Repeats within 24 h return the original response.
- **Pagination:** cursor-based. `?limit=50&cursor=<opaque>`. Response `{ "items": [...], "next_cursor": "..." | null }`.
- **Concurrency:** blackboard and settings writes use `If-Match: <version>`. A mismatch returns `412`.
- **Errors:** RFC 7807 `application/problem+json`:
```json
{ "type": "https://titan.local/errors/session-already-live", "title": "Another session is live",
  "status": 409, "code": "SESSION_ALREADY_LIVE", "detail": "Session 0193... is live; stop it first.",
  "instance": "/api/v1/sessions/0193.../start", "errors": [ { "field": "game_profile_id", "message": "..." } ] }
```
**Error codes** (`titan_core.errors.ErrorCode`): `VALIDATION_FAILED` 422, `NOT_FOUND` 404, `UNAUTHORIZED` 401, `CONFLICT` 409, `SESSION_ALREADY_LIVE` 409, `INVALID_STATE_TRANSITION` 409, `VERSION_MISMATCH` 412, `DEPENDENCY_UNAVAILABLE` 503 (with `detail.dependency` set to `ollama`, `obs`, `postgres`, `redis`, `chroma`, or `game`), `INTEGRATION_MISSING` 424, `INSUFFICIENT_DISK` 507, `SAFETY_LOCKED` 423, `NOT_IMPLEMENTED_IN_PHASE` 501, `RATE_LIMITED` 429, `INTERNAL` 500.

### 5.2 REST endpoints

#### System
| Method | Path | Request | Response 200 |
|---|---|---|---|
| GET | `/health` | none | `{"status":"ok"}` |
| GET | `/system/status` | none | `{"services":[{"name":"postgres","state":"up","pid":1234,"restarts":0,"since":"..."}],"dependencies":{"ollama":{"state":"up","version":"0.x"},"obs":{"state":"down"}},"resource_guard_level":"L0"}` |
| GET | `/system/metrics` | none | `SystemMetrics` (Section 5.3) |
| POST | `/system/diagnostics` | none | `202 {"job_id"}`, producing a zip with secrets stripped |

`ServiceState` = `{name, state, pid, restarts, since, detail, kind}`. `state` is `up`, `degraded` (running but failing health checks, or Redis without `requirepass`), `starting`, `down` (waiting for a restart), `failed` (circuit open: restarts stopped until a manual restart), `stopped`, or `unknown` (not started yet; `detail` says what it waits for). `kind` is `managed`, `external` (health-checked only, such as Memurai as a Windows service) or `oneshot` (migrations). `services` comes from the supervisor; without one (the API started by hand) it lists only `api`. `dependencies` covers `postgres`, `redis`, `chroma`, `ollama` and `obs`, each check bounded to 1 s. `/system/metrics` returns `404` until the supervisor has published a first sample and `503` (`dependency: redis`) when Redis is down.

#### Supervisor RPC (internal, `http://127.0.0.1:8769`)
Bearer launch token on every route except `/health`. Callers: Electron main (boot splash, quit), the API (`/system/status`), and later the session controller.

| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/health` | none | `{"status":"ok"}` |
| GET | `/status` | `?since=<event seq>` | `SupervisorStatus` `{started_at, ready, services:[ServiceState], events:[{seq, ts, process, kind, detail}]}`. Event kinds: `starting`, `healthy`, `unhealthy`, `exited`, `restarting`, `circuit_open`, `stopped`, `adopted` |
| POST | `/processes/{name}/restart` | none | `202`. Also closes an open circuit |
| GET | `/metrics/latest` | none | `SystemMetrics` |
| PUT | `/metrics/game` | `{"pid": 1234 \| null}` | Points PresentMon at the game process (the session controller calls this on session start) |
| POST | `/shutdown` | none | `202`. Stops every process in reverse start order, then exits |

#### Settings and models
| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/settings` | none | `{"version":3,"values":{...}}` |
| PATCH | `/settings` | `If-Match`. JSON Merge Patch | Updated settings |
| GET | `/models` | none | `{"providers":[{"id":"ollama","healthy":true,"models":[{"name":"qwen3:8b","size_mb":5200,"loaded":true}]}]}` |
| POST | `/models/pull` | `{"provider":"ollama","model":"qwen3:8b"}` | `202 {"job_id"}`, progress on WS `jobs` |
| GET | `/models/routes` | none | `{"profile":"vram_12gb","roles":{"director":{"provider":"ollama","model":"qwen3:8b"}}}` |
| PUT | `/models/routes` | Same shape | Updated. Validated against installed models |

#### Games and discovery
| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/games` | none | `{"items":[Game]}` |
| POST | `/games/scan` | `{"stores":["steam","epic","gog"],"extra_paths":[]}` | `{"detected":[{"game_slug":"ksp","profile_id":"...","store":"steam","install_path":"...","game_version":"..."}],"unmatched":[]}` |
| GET | `/games/{game_id}` | none | `Game` with `profiles` |
| PATCH | `/game-profiles/{profile_id}` | `{"is_default":true,"launch_args":[]}` | `GameProfile` |
| POST | `/game-profiles` | `{"game_slug":"ets2","executable_path":"D:/..."}` | `201 GameProfile` (standalone) |
| GET | `/game-profiles/{profile_id}/integration` | none | `{"status":"missing","details":{"required":"scs-sdk-plugin 1.12.1","found":null},"instructions_md":"..."}` |
| POST | `/game-profiles/{profile_id}/integration/install` | `{"consent":true}` | `{"status":"installed"}`. Copies the pinned, hash-verified plugin |
| POST | `/game-profiles/{profile_id}/launch` | none | `202 {"pid":null,"method":"steam_uri"}` |
| GET | `/games/{game_id}/controls` | `?context=flight` | `{"items":[ControlBinding]}` |
| PUT | `/games/{game_id}/controls/{binding_id}` | `ControlBinding` | `ControlBinding` (`source` becomes `user`) |
| GET | `/games/{game_id}/risks` | none | `{"items":[RiskEntry]}` |
| GET | `/games/{game_id}/strategies` | `?status=active` | `{"items":[Strategy]}` |

`Game` = `{id, slug, name, domain, genres, capabilities, research_status, profiles?: GameProfile[]}`.
`GameProfile` = `{id, game_id, store, install_path, executable_path, game_version, telemetry_status, is_default, last_seen_at}`.

#### Sessions
| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/sessions` | `CreateSession` | `201 Session` |
| GET | `/sessions` | `?game_id&state&limit&cursor` | Paged `Session` |
| GET | `/sessions/{sid}` | none | `Session` plus `{agents:[AgentInstance], recording?: Recording, missions:[Mission]}` |
| POST | `/sessions/{sid}/start` | `{"launch_game":true}` | `202 Session{state:"starting"}`. Errors: `SESSION_ALREADY_LIVE`, `DEPENDENCY_UNAVAILABLE`, `INTEGRATION_MISSING` |
| POST | `/sessions/{sid}/pause` | none | `Session{state:"paused"}`. Agents are paused. Telemetry and recording continue |
| POST | `/sessions/{sid}/resume` | none | `Session{state:"live"}` |
| POST | `/sessions/{sid}/stop` | `{"outcome":"success"}` (optional user verdict) | `202 Session{state:"stopping"}`. The end report arrives as event `session.ended` |
| GET | `/sessions/{sid}/events` | `?from_ms&to_ms&type&category&min_severity&cursor` | Paged `GameEvent` |
| GET | `/sessions/{sid}/messages` | `?from_ms&to_ms&type&sender&visibility&cursor` | Paged `Envelope` |
| GET | `/sessions/{sid}/telemetry` | `?from_ms&to_ms&resolution=1s` | `{"items":[TelemetryFrame]}` (from `telemetry_samples`) |
| GET | `/sessions/{sid}/report` | none | `SessionReport` (Section 6.10). `404` until the session ends |
| POST | `/sessions/{sid}/chat` | `{"text":"Gene, are we good on fuel?","to":["persona:gene"] }` | `202 {"message_id"}`. Becomes `user.say` on the bus |

`CreateSession` = `{"game_id":"...","game_profile_id":"...","team_id":null,"title":"First orbit attempt","mode":"observe","settings":{"recording_preset":"1080p60","record":true,"webcam":true,"agents_enabled":true,"model_profile":"vram_12gb"},"replay_of_session_id":null,"missions":[{"title":"Reach orbit","objective":"Periapsis above 70 km","success_criteria":[{"path":"vehicle.orbit.periapsis_m","op":">","value":70000}]}]}`. Mode `autonomous` returns `NOT_IMPLEMENTED_IN_PHASE` in P1. Mode `replay` requires `replay_of_session_id` or a fixture path in `settings.replay_fixture`.

`Session` = `{id, game_id, game_profile_id, team_id, title, mode, state, started_at, ended_at, outcome, data_dir, settings}`.

#### Missions, agents, teams, personas
| Method | Path | Request | Response |
|---|---|---|---|
| POST | `/sessions/{sid}/missions` | `{title, objective, success_criteria, failure_criteria, priority, parent_mission_id?}` | `201 Mission` |
| PATCH | `/missions/{mid}` | `{status?, priority?, title?}` | `Mission` |
| GET | `/personas` | `?game_id&department` | `{"items":[Persona]}` |
| POST | `/personas` | `Persona` (without id) | `201 Persona` (`source:"user"`) |
| PATCH | `/personas/{pid}` | partial | `Persona` (`version+1`) |
| GET | `/teams` | `?game_id` | `{"items":[Team{agents:[Agent]}]}` |
| POST | `/teams` | `{game_id, name, purpose, agents:[{persona_id, role, responsibilities, tools, event_subscriptions, tick_interval_ms, can_commentate}]}` | `201 Team` |
| GET | `/sessions/{sid}/agents` | none | `{"items":[AgentInstance]}` |
| POST | `/sessions/{sid}/agents` | `{"agent_id":"..."}` | `202 AgentInstance{state:"spawning"}` (user-initiated spawn) |
| DELETE | `/sessions/{sid}/agents/{instance_id}` | `?reason=` | `202`. Graceful terminate (Section 6.6) |
| POST | `/sessions/{sid}/agents/{instance_id}/mute` | `{"muted":true}` | `AgentInstance`. A muted agent cannot take the floor |

`AgentInstance` = `{id, agent_id, role, persona:{slug, display_name, color_hex, portrait_url}, state, model_resolved, tokens_in, tokens_out, messages_sent, muted}`.

#### Blackboard
| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/sessions/{sid}/blackboard` | `?sections=goals,facts&since_version=` | `{"bb_version":812,"entries":[BBEntry]}` |
| GET | `/sessions/{sid}/blackboard/{section}/{key}/history` | none | `{"items":[BBEntry]}` |
| PUT | `/sessions/{sid}/blackboard/{section}/{key}` | `If-Match: <version or 0>`. `{"value":{...},"confidence":1.0}` | `BBEntry`. User writes are allowed on `goals`, `notes`, `facts` only. `world_state` returns `403` |
| DELETE | `/sessions/{sid}/blackboard/{section}/{key}` | `If-Match` | `BBEntry{op:"retract"}` |

`BBEntry` = `{section, key, version, op, value, author, confidence, evidence, bb_version, created_at, expires_at}`.

#### Memory and knowledge
| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/memories/search` | `?game_id&q&tier&agent_id&k=10` | `{"items":[{"memory":Memory,"score":0.81}]}` |
| GET | `/memories` | `?game_id&session_id&tier&cursor` | Paged `Memory` |
| POST | `/memories` | `{game_id, tier, kind, content, importance}` | `201 Memory` (user-authored) |
| DELETE | `/memories/{id}` | none | `204` (also removed from Chroma) |
| GET | `/knowledge/search` | `?game_id&q&kind&k=10` | `{"items":[{"entry":KnowledgeEntry,"chunk":"...","score":0.77}]}` |
| POST | `/knowledge` | `{game_id, kind, title, body, structured?}` | `201 KnowledgeEntry` (`source_kind` user, `verified:true`) |
| POST | `/memory/reindex` | `{"collections":["memories"]}` | `202 {"job_id"}` |

#### Recording
| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/recording/devices` | none | `{"cameras":[{"id":"...","name":"Logitech BRIO"}],"microphones":[...],"obs":{"connected":true,"version":"30.2"}}` |
| POST | `/sessions/{sid}/recording/start` | `{"preset":"1080p60","tracks":["gameplay_video","game_audio","mic_audio","webcam_video"]}` | `202 Recording{state:"starting"}`. Errors: `INSUFFICIENT_DISK`, `DEPENDENCY_UNAVAILABLE(obs)` |
| POST | `/sessions/{sid}/recording/stop` | none | `202 Recording{state:"stopping"}` |
| GET | `/recordings/{rid}` | none | `Recording{tracks:[Track]}` |
| POST | `/recordings/{rid}/markers` | `{"t_ms":null,"kind":"user","label":"Nice landing"}` (`t_ms` null means now) | `201 Marker` |
| GET | `/recordings/{rid}/markers` | none | `{"items":[Marker]}` |

#### Safety
| Method | Path | Request | Response |
|---|---|---|---|
| GET | `/safety/state` | none | `SafetyState` |
| POST | `/safety/kill` | `{"source":"hotkey"}` | `200 SafetyState{armed:false, killed:true}`. Must answer in under 50 ms |
| POST | `/safety/resume` | `{"confirm":"RESUME"}` | `SafetyState{killed:false, armed:false}`. Re-arming is a separate P4 call |
| POST | `/safety/arm` (P4) | `{"session_id","confirm":"ARM"}` | `SafetyState{armed:true}`. In P1 always returns `SAFETY_LOCKED` |

`SafetyState` = `{killed, armed, control_owner:"none|ai|human", last_kill_at, last_kill_source, policy_version}`.

#### Jobs and later phases
- `GET /jobs/{job_id}` returns `{id, kind, state:"queued|running|succeeded|failed|cancelled", progress:0..1, result, error}`. `DELETE /jobs/{job_id}` cancels a job.
- Reserved and returning `501` in P1: `POST /games/{id}/research` (P2), `POST /games/{id}/factory/generate-team` (P3), `/video-projects*` (P6), `/video-projects/{id}/thumbnails*` (P7), `/upload-jobs*` (P7), `/accounts/youtube/oauth/start|callback` (P7), `/analytics*` (P8). Their shapes follow Section 4 rows and are defined in the phase that builds them.

### 5.3 WebSocket protocol
One connection: `ws://127.0.0.1:8765/api/v1/ws`. The first client frame must be `auth` within 3 s or the server closes with code `4401`. A valid `auth` is answered with `{"op":"ack","req_id":"auth","ok":true}`. Connections whose `Origin` header is not in `api.cors_origins` are refused (close `1008`); clients that send no `Origin` (Node, tests) still need the token. `system.metrics` starts with the newest sample (metrics are latest-wins, so older ones are not replayed). In Phase 1, `session.*` subscriptions are answered `NOT_FOUND` until sessions exist (M2).

**Client to server frames:**
```json
{ "op": "auth", "token": "<launch_token>", "client": "desktop/1.0.0" }
{ "op": "subscribe", "req_id": "r1", "channel": "session.0193abcd.chat", "since_seq": "1731090000000-0" }
{ "op": "unsubscribe", "req_id": "r2", "channel": "session.0193abcd.telemetry" }
{ "op": "ping", "req_id": "r3" }
```
**Server to client frames:**
```json
{ "op": "ack", "req_id": "r1", "ok": true }
{ "op": "ack", "req_id": "r1", "ok": false, "error": { "code": "NOT_FOUND", "detail": "unknown session" } }
{ "op": "msg", "channel": "session.0193abcd.chat", "seq": "1731090001234-0", "ts": "2026-11-08T19:30:01.234Z", "type": "chat.delta", "data": { } }
{ "op": "pong", "req_id": "r3" }
{ "op": "gap", "channel": "...", "from_seq": "...", "reason": "trimmed" }
```
`seq` is the Redis stream ID. On reconnect the client sends `since_seq` with the last seen seq per channel. If that data has been trimmed, the server sends `gap` and the client refetches over REST.

**Channels and message types:**
| Channel | Rate | `type` values and `data` shape |
|---|---|---|
| `session.{sid}.chat` | event-driven | `chat.start` `{message_id, sender:{instance_id, persona_slug, display_name, role, color_hex, portrait_url}, reply_to, event_ref, kind:"say"}`. `chat.delta` `{message_id, delta}`. `chat.final` `{message_id, text, tokens, model, latency_ms, mentions:[...]}`. `chat.cancelled` `{message_id, reason}`. `user.say` `{message_id, text, to}`. `system.notice` `{text, level}` |
| `session.{sid}.agents` | event-driven | `agent.state` `{instance_id, state, reason?}`. `task.update` `{task_id, state, assignee_instance_id, title}`. `floor.state` `{holder_instance_id \| null, queue:[instance_id]}`. `bb.update` `{section, key, version, author}` (no value; fetch on demand) |
| `session.{sid}.telemetry` | **coalesced at 10 Hz max, latest-wins** | `telemetry.frame` `TelemetryFrameUI` (Section 7.2, `game_specific` omitted unless `?full=1` was sent in subscribe as `"options":{"full":true}`) |
| `session.{sid}.events` | event-driven | `game.event` `GameEvent` (Section 7.4). `session.state` `{state, outcome?}`. `session.ended` `{report_url}` |
| `session.{sid}.recording` | 1 Hz plus on change | `recording.status` `RecordingStatus` (below) |
| `system.metrics` | 1 Hz | `system.metrics` `SystemMetrics` |
| `system.safety` | on change | `safety.state` `SafetyState` |
| `jobs` | on change | `job.update` `{id, kind, state, progress, error?}` |

```jsonc
// RecordingStatus
{ "recording_id": "0193...", "state": "recording", "elapsed_ms": 742113,
  "obs_connected": true, "disk_free_bytes": 412000000000, "est_remaining_min": 610,
  "tracks": [ { "kind": "gameplay_video", "state": "recording", "bytes": 5123456789, "bitrate_kbps": 48000, "dropped_frames": 3, "fps": 60.0 },
              { "kind": "webcam_video",   "state": "recording", "bytes": 812345678,  "bitrate_kbps": 9000,  "dropped_frames": 0, "fps": 30.0 },
              { "kind": "mic_audio",      "state": "recording", "level_dbfs": -18.2 } ] }
// SystemMetrics
{ "ts": "...", "game_fps": 71.8, "game_frametime_p99_ms": 21.4, "cpu_pct": 38.1, "ram_used_mb": 21450, "ram_total_mb": 65456,
  "gpu": [{ "index": 0, "name": "RTX 4070", "util_pct": 81, "vram_used_mb": 9850, "vram_total_mb": 12282, "temp_c": 67, "encoder_util_pct": 12 }],
  "tokens_per_min": 4120, "llm_queue_depth": 2, "goals_active": 2, "tasks_open": 5, "resource_guard_level": "L0" }
```
Backpressure: each connection has a 512-frame send buffer. Telemetry is dropped first (latest-wins), then `agents`. `chat` and `events` are never dropped. If they would overflow, the server closes with `4408` and the client resumes from `since_seq`.

---

## 6. Agent communication protocol

### 6.1 Envelope
Every message on `titan:s:{sid}:bus` is an `Envelope`. The Pydantic model in `titan_core.protocol.envelope` is the source. Its generated JSON Schema, shown condensed (the committed `schemas/envelope.json` is semantically equivalent: Pydantic writes nullable fields as `anyOf: [..., {"type": "null"}]` and includes defaults; the contract samples in `tests/contract/` are validated against both the Python models and the zod schemas):

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://titan.local/schemas/envelope.json",
  "title": "Envelope",
  "type": "object",
  "required": ["id","schema","type","session_id","ts","t_mono_ns","sender","recipients","visibility","priority","payload"],
  "additionalProperties": false,
  "properties": {
    "id":             { "type": "string", "format": "uuid", "description": "UUIDv7" },
    "schema":         { "const": "titan.msg/1" },
    "type":           { "type": "string", "pattern": "^[a-z]+(\\.[a-z_]+)+$" },
    "session_id":     { "type": "string", "format": "uuid" },
    "mission_id":     { "type": ["string","null"], "format": "uuid" },
    "ts":             { "type": "string", "format": "date-time" },
    "t_mono_ns":      { "type": "integer" },
    "sender":         { "$ref": "#/$defs/Address" },
    "recipients":     { "type": "array", "minItems": 1, "items": { "type": "string",
                        "pattern": "^(broadcast|director|instance:[0-9a-f-]{36}|role:[a-z_]+|team:[a-z_]+|persona:[a-z0-9_.-]+|user|system)$" } },
    "correlation_id": { "type": ["string","null"], "format": "uuid", "description": "Conversation/task thread id" },
    "causation_id":   { "type": ["string","null"], "format": "uuid", "description": "Envelope that caused this one" },
    "reply_to":       { "type": ["string","null"], "format": "uuid" },
    "visibility":     { "enum": ["public","internal"], "description": "public = shown in Agents panel" },
    "priority":       { "type": "integer", "minimum": 0, "maximum": 9, "description": "9 = highest" },
    "ttl_ms":         { "type": ["integer","null"], "minimum": 0 },
    "payload":        { "type": "object", "description": "Schema selected by `type` (Sec 6.2)" }
  },
  "$defs": {
    "Address": { "type": "object", "required": ["kind","id"], "additionalProperties": false,
      "properties": {
        "kind": { "enum": ["agent","director","system","user","adapter","safety"] },
        "id":   { "type": "string", "description": "instance uuid, 'director', 'system', 'user', adapter slug" },
        "role": { "type": "string" },
        "persona_slug": { "type": "string" } } }
  }
}
```

### 6.2 Message types and payloads
Payloads are written as TypeScript types for brevity. The Pydantic equivalents live in `titan_core/protocol/payloads.py`.

```ts
// ---- Tasks (Director <-> agents)
type TaskAssign   = { task_id: UUID; kind: TaskKind; title: string; input: Json; mission_id?: UUID;
                      deadline_ms: number; priority: number; acceptance: string };   // what "done" means
type TaskAccept   = { task_id: UUID; eta_ms?: number };
type TaskReject   = { task_id: UUID; reason: "busy" | "out_of_scope" | "missing_input" | "unsafe"; detail?: string };
type TaskProgress = { task_id: UUID; progress: number /*0..1*/; note?: string };
type TaskBlocked  = { task_id: UUID; needs: string; from_role?: string };
type TaskComplete = { task_id: UUID; output: Json; summary: string; bb_refs: BBRef[] };
type TaskFail     = { task_id: UUID; reason: string; retryable: boolean };
type TaskCancel   = { task_id: UUID; reason: string };
type TaskEvaluate = { task_id: UUID; score: number /*0..1*/; notes: string };        // Director -> log

// ---- Blackboard notifications (writes happen through BlackboardService, which emits these)
type BBWritten    = { section: Section; key: string; version: number; op: "put" | "retract"; bb_version: number };
type ConflictRaised = { section: Section; key: string; versions: number[]; authors: string[]; summary: string };

// ---- Queries between agents (always via the bus; answered within ttl or dropped)
type QueryAsk     = { question: string; context_refs?: BBRef[] };
type QueryAnswer  = { answer: string; confidence: number; bb_refs?: BBRef[] };

// ---- Conversation (shown in Agents panel when visibility=public)
type ChatSay      = { text: string; kind: "say" | "aside"; event_ref?: UUID; mentions?: string[];
                      tokens?: number; model?: string; latency_ms?: number };
type ChatDelta    = { message_id: UUID; delta: string };                              // streaming chunk of a ChatSay
type UserSay      = { text: string; to: string[] };

// ---- Floor control (commentary turn-taking)
type FloorRequest = { urgency: number /*0..1*/; topic: string; event_ref?: UUID; est_words: number };
type FloorGrant   = { request_id: UUID; max_words: number; deadline_ms: number };
type FloorDeny    = { request_id: UUID; reason: "busy" | "cooldown" | "low_urgency" | "muted" | "stale" };
type FloorRelease = { request_id: UUID; spoke: boolean };
type FloorPreempt = { holder: string; reason: "critical_event" | "user_speaking" | "kill" };

// ---- Lifecycle
type AgentSpawn     = { agent_id: UUID; instance_id: UUID; reason: string };           // director/system -> system
type AgentReady     = { instance_id: UUID; model: string; tools: string[] };
type AgentHeartbeat = { instance_id: UUID; state: AgentState; inbox_depth: number; open_tasks: number };
type AgentTerminate = { instance_id: UUID; reason: "session_end" | "director_retire" | "user" | "crash_loop" | "resource_guard"; grace_ms: number };
type AgentTerminated= { instance_id: UUID; reason: string; final_report?: string };

// ---- Game and world
type GameEventMsg   = GameEvent;                                                       // mirrored from events stream for agents
type WorldStateTick = { bb_version: number; scene: string; summary: Json };            // 1 Hz, internal

// ---- Actions (P4; schema frozen now, rejected by titan-actions in P1)
type ActionPropose  = { action_id: string; params: Json; rationale: string; risk: "low" | "medium" | "high" | "irreversible"; expected_effect: string };
type ActionDecision = { proposal_id: UUID; decision: "approved" | "denied"; by: "director" | "policy" | "user"; reason?: string };
type ActionExecuted = { proposal_id: UUID; ok: boolean; latency_ms: number; error?: string };

// ---- Safety (also on pub/sub)
type SafetyKill     = { source: "hotkey" | "ui" | "api" | "watchdog" | "policy"; detail?: string };
type SafetyOverride = { control_owner: "human" | "ai" | "none"; reason: string };
type SafetyResume   = { by: "user" };

// ---- Session
type MissionUpdate  = { mission_id: UUID; status: MissionStatus; note?: string };
type DirectorReport = { period_s: number; goals: string[]; progress: string; issues: string[]; next: string[] };
type BBRef          = { section: Section; key: string; version: number };
```

| `type` | Sender | Recipients | Visibility | Priority |
|---|---|---|---|---|
| `task.assign` / `task.cancel` / `task.evaluate` | director | `instance:*` | internal | 6 |
| `task.accept` / `task.reject` / `task.progress` / `task.blocked` / `task.complete` / `task.fail` | agent | director | internal | 5 |
| `bb.written` / `conflict.raised` | system | broadcast / director | internal | 3 / 7 |
| `query.ask` / `query.answer` | agent | `role:*` / `instance:*` | internal (public if `kind=aside`) | 4 |
| `chat.say` / `chat.delta` | agent, director | broadcast | public | 5 |
| `user.say` | user | broadcast or named | public | 8 |
| `floor.request` / `floor.release` | agent | system | internal | 5 |
| `floor.grant` / `floor.deny` / `floor.preempt` | system | `instance:*` | internal | 7 |
| `agent.spawn` / `agent.terminate` | director, system, user | system / `instance:*` | internal | 6 |
| `agent.ready` / `agent.heartbeat` / `agent.terminated` | agent | system | internal | 2 |
| `game.event` | adapter | broadcast | internal (the UI gets it via `events` channel) | from severity |
| `world.tick` | system | broadcast | internal | 1 |
| `action.propose` / `action.decision` / `action.executed` | agent / director / actions | director / agent | internal | 8 |
| `safety.kill` / `safety.override` / `safety.resume` | safety, user | broadcast | public (`system.notice`) | 9 |
| `mission.update` / `director.report` | director | broadcast | public | 6 |

**Delivery rules:** the router resolves `role:`, `team:`, and `persona:` to live instances. Envelopes past `ttl_ms` are dropped at dequeue. Each inbox processes in priority order, then FIFO. `safety.*` bypasses inboxes and is handled by the runtime directly (cancel LLM calls, release floor).

### 6.3 Ordering, delivery, and persistence
- **Order:** total order per session through the bus stream. Agents must not rely on order across `correlation_id`s.
- **Delivery:** at-least-once to the persister (consumer group with `XACK` after the Postgres commit; idempotent through `agent_messages.id` PK with `ON CONFLICT DO NOTHING`). At-most-once to agent inboxes (live only; after a restart agents rebuild context from the blackboard, not by replaying chat).
- **Size limit:** an envelope is at most 32 KB. Larger data goes on the blackboard or in files, and the envelope carries a reference.

### 6.4 Blackboard semantics
The blackboard is a per-session, sectioned key-value store. The current state is cached in Redis hashes. Postgres `blackboard_entries` holds the full append-only history. **All access goes through `BlackboardService`** (in the orchestrator; the API calls it over the bus with request-reply `bb.request` / `bb.response` internal messages, timeout 2 s).

| Section | Writers | Shape of `value` | TTL default |
|---|---|---|---|
| `goals` | director, user | `{title, status:"active\|done\|dropped", mission_id?, priority}` | none |
| `plan` | director, planner roles | `{steps:[{n, text, owner_role, status}], rationale}` | none |
| `tasks` | system (mirror of `tasks` table) | `{task_id, state, assignee, title}` | none |
| `world_state` | **system only** (WorldStateUpdater) | adapter `world_state_summary()` plus derived values | overwritten at 1 Hz |
| `facts` | agents, user | `{statement, data?, unit?}` | 10 min (refreshable) |
| `hypotheses` | agents | `{statement, test?}` | 5 min |
| `risks` | agents, system (risk rules) | `{risk_id?, title, severity 1-5, eta_s?, mitigation}` | until retracted |
| `discoveries` | agents | `{statement, evidence}`, which becomes a memory candidate at session end | none |
| `lessons` | director, session_end | `{lesson, applies_when}` | none |
| `notes` | user | free text | none |

**Operations:**
- `get(section, key)` returns `BBEntry | None`. `snapshot(sections, since_bb_version=None)` returns the entries plus the current `bb_version`. Reads are lock-free from Redis and always reflect committed writes (write-through: Postgres first, then Redis, then `bb.written`).
- `put(section, key, value, author, expected_version, confidence, evidence, ttl_s)`. Compare-and-set: `expected_version=0` means "create only", `-1` means "unconditional" (system and director only). A mismatch returns `VersionMismatch(current)`. The agent re-reads and may retry once.
- `retract(section, key, author, expected_version)` writes an `op=retract` version.
- **Permissions:** checked against `agents.bb_write_sections` plus the table above. Agents may only modify keys they created, unless they are the director or the section is `risks` (anyone may raise; only the author or the director may retract).
- **Conflicts:** if a `facts` put supersedes another author's entry and the values differ beyond a tolerance (numbers 5%, text by LLM-free string inequality), the service emits `conflict.raised` to the director, who resolves it on the next tick by writing the authoritative version with `evidence` pointing to telemetry.
- **Key naming:** `<domain>.<name>`, for example `fuel.stage_dv_ms`, `route.next_fuel_stop`, `risk.overheat_engine_2`.
- **Write rate limits:** 20 writes/min per agent instance. Excess gets `RATE_LIMITED` and an audit event.

### 6.5 Director: task assignment lifecycle
```
            assign            accept            start work
 proposed ---------> assigned ------> accepted ---------> in_progress ----> completed --> (evaluated)
    |                   |  \reject/timeout(10s)            |   ^   \
    |                   v                                   |   |    \--> failed --(attempts<max)--> proposed
    |              proposed (reassign to next best)         v   |
    |                                                    blocked (needs X; director resolves)
    '--> cancelled (any non-terminal state, by director/user/session end)
 deadline passes in accepted/in_progress/blocked --> timed_out --(attempts<max)--> proposed
```
- **Selection:** the Director picks an assignee by `role` match first. Ties go to the instance with the fewest open tasks, then the best `agents.stats.avg_eval`. Each instance has at most 2 open tasks.
- **Timers:** accept within 10 s. Default `deadline_ms` is 60 s for `compute`/`explain` and 300 s for `plan`/`monitor`. `monitor` tasks are long-running and complete on mission end.
- **Evaluation:** on `task.complete`, the Director scores the output (an LLM rubric call at P2 priority, or a rule if the task has a machine-checkable `acceptance`). It stores `tasks.evaluation` and updates `agents.stats`.
- **Phase 1 Director duties:** keep `goals` and `plan` current for the active mission, assign analysis and monitoring tasks, resolve conflicts, raise mission success or failure from criteria, and post a `director.report` (public, 1 to 2 sentences) every 5 minutes or on a mission change. The Director never takes the commentary floor more than once per 60 s.
- **Phase 3+:** the Director can recruit (spawn an agent from the team or factory) and retire (`status: probation` after 3 evaluations under 0.4; `retired` after probation fails). This is gated by setting `director.can_spawn` (P1 default `false`).

### 6.6 Agent lifecycle
```
spawning --(graph compiled, model resolved, agent.ready)--> ready <--> busy
   |                                                         |  ^
   | (init error x3)                                         v  |
   '--> crashed  <--(unhandled exception; auto-restart once)-- paused (session paused / resource guard L4)
ready|busy|paused --(agent.terminate, grace_ms default 5s: finish/abort current LLM call,
                    release floor, hand back open tasks as 'proposed')--> terminating --> terminated
```
- **Spawn sources:** session start (team roster), user (REST), Director (P3+).
- **Heartbeat:** every 5 s. Three missed heartbeats mark the instance `crashed`. The runtime restarts it once from its LangGraph checkpoint. A second crash within 10 minutes means `terminated` with reason `crash_loop`.
- On session end, every agent gets `agent.terminate(reason="session_end")`, then `session_end.py` runs (Section 6.10).

### 6.7 Commentary turn-taking (Floor Manager)
There is one floor per session. Only the floor holder may emit `chat.say` with `kind="say"`. `aside` (short, 12 words or fewer, internal-to-public banter) is limited to 1 per 30 s per agent and also requires the floor.

**Scoring a `floor.request`:**
```
score = 0.45*urgency + 0.20*role_relevance(event_type, role) + 0.15*time_since_last_spoke_norm
      + 0.10*persona_talkativeness - 0.20*repetition_risk - 0.10*same_speaker_as_last
```
`role_relevance` comes from the team template's `topics` per role. `repetition_risk` is the max cosine similarity of the `topic` to the last 10 utterances.

**Rules:**
| Rule | Value |
|---|---|
| Arbitration window after an event | 300 ms (collect requests, grant the highest score) |
| Minimum gap between utterances | 1.5 s |
| Max words per grant | 30 (P1 text). Director: 40 |
| Grant deadline (first token) | 2.5 s, else the grant is revoked and `floor.deny(stale)` |
| Same speaker twice in a row | Only if no other request with score 0.4 or more is pending |
| Idle chatter | If no speech for 45 s and the game is not paused, the Floor Manager invites the agent with the highest `talkativeness` and `time_since_last_spoke` to make an observation |
| Pre-emption | An event with `severity=critical` (crash, vessel destroyed, collision) pre-empts the holder: cancel the stream, emit `chat.cancelled`, and grant the most relevant role at once |
| User speaks (`user.say`) | Pre-empts. The addressed persona, or the Director if none, gets the floor next with `urgency=1` |
| Game paused | Floor closed except for replies to `user.say` |
| Anti-repetition | Before `chat.final`, the text is checked against the `commentary` collection (Section 4.3). Over 0.92 means one regeneration with the prior line quoted as "do not repeat". A second failure drops the utterance |
| Grounding | Every utterance about numbers must use values from `world_state` or `facts` in its context. The prompt template enforces "Never invent telemetry values". A post-check regex compares cited numbers to `world_state` within 10% and drops mismatches (logged as `commentary.ungrounded`) |

Banter (Phase 5 "arguments and humor") is built on the same mechanism. A granted speaker may set `mentions:["persona:x"]`, which adds +0.3 urgency to that persona's next request within 10 s, producing natural back-and-forth.

### 6.8 Worked examples

**KSP: max-Q during ascent (Phase 1, observe mode)**
1. `titan-telemetry` detects a dynamic-pressure peak (rule `ksp.max_q`). It XADDs to `events`:
```json
{ "id": "0193f1a2-7c00-7000-8000-000000000001", "type": "ksp.max_q", "category": "game", "severity": "notice",
  "salience": 0.7, "t_session_ms": 84210, "payload": { "dynamic_pressure_pa": 28750, "altitude_m": 11240, "speed_mps": 402 } }
```
2. The orchestrator EventRouter delivers `game.event` to subscribers (`flight_engineer`, `mission_planner`, director). The Flight Engineer (persona "Gene") sends:
```json
{ "id": "0193f1a2-7c10-7000-8000-000000000002", "schema": "titan.msg/1", "type": "floor.request",
  "session_id": "0193f19c-0000-7000-8000-00000000aaaa", "ts": "2026-11-08T19:41:24.330Z", "t_mono_ns": 912345678901234,
  "sender": { "kind": "agent", "id": "0193f19c-1111-7000-8000-000000000e01", "role": "flight_engineer", "persona_slug": "ksp.flight_engineer.gene" },
  "recipients": ["system"], "causation_id": "0193f1a2-7c00-7000-8000-000000000001", "visibility": "internal", "priority": 5, "ttl_ms": 2000,
  "payload": { "urgency": 0.7, "topic": "max-Q passed, structure held", "event_ref": "0193f1a2-7c00-7000-8000-000000000001", "est_words": 20 } }
```
3. The Floor Manager grants (`floor.grant {max_words:30, deadline_ms:2500}`). Gene streams `chat.delta` and then `chat.say`: *"Max-Q at 28.7 kilopascals and nothing fell off. I'll take it. Throttle back up."*
4. In parallel, the Director (on its event trigger) sends `task.assign` to the Mission Planner:
```json
{ "type": "task.assign", "sender": { "kind": "director", "id": "director" }, "recipients": ["role:mission_planner"],
  "correlation_id": "0193f1a2-7d00-7000-8000-0000000000c1", "visibility": "internal", "priority": 6,
  "payload": { "task_id": "0193f1a2-7d00-7000-8000-0000000000c1", "kind": "compute", "title": "Estimate circularization burn",
               "input": { "target_periapsis_m": 80000 }, "deadline_ms": 60000, "priority": 6,
               "acceptance": "bb facts key burn.circularize with dv_ms and burn_time_s" } }
```
5. The Planner accepts, calls adapter tool `ksp.vis_viva_dv` (read-only calculator), and writes `facts/burn.circularize = {"dv_ms": 912, "burn_time_s": 38, "start_at_apoapsis_minus_s": 19}` with `expected_version=0` and evidence `[{type:"telemetry", t_session_ms:84210}]`. Then it sends `task.complete`. The Director evaluates it (rule: key exists with the required fields, score 1.0).
6. Later, `ksp.vessel_destroyed` (critical) pre-empts the floor. Commentary goes to the Director/Host first, and a `failure` memory candidate is written to `discoveries`.

**ETS2: low fuel on a delivery (Phase 1, observe mode)**
1. Rule `vehicle.fuel_low` fires (`fuel.ratio < 0.15` sustained 5 s). Event severity `warning`, salience 0.6, payload `{fuel_l: 61, range_km: 148, nav_distance_remaining_km: 212}`.
2. The Director creates a task for the `route_planner`: "Find nearest fuel stop on route". The Route Planner has no map API in P1, so it answers from telemetry and knowledge: it writes `risks/fuel.short_of_destination = {severity: 3, eta_s: 5400, mitigation: "refuel within 140 km"}` and `facts/fuel.range_km = 148`.
3. The Economy Manager (persona "Penny") requests the floor with topic "fuel cost versus delivery bonus". It is granted: *"We're 64 km short of Krakow. Refuelling now costs about EUR 95. Being late costs us the whole bonus. Fill up."*
4. Event `scs.player.fined {offence: "speeding", amount: 250}` arrives within 20 s. The Economy Manager's `mentions:["persona:ets2.driver_coach.max"]` boosts Max (Driver Coach), who gets the next turn: *"In my defence, the sign was very small."* The Director writes `lessons/speed.fines = {lesson: "Speeding fines cost 2.6x the fuel stop", applies_when: "speed_limit_known"}`.

### 6.9 Safety rails for game input
Phase 1 has **no input path at all**. `titan-actions` does not start, `agents.can_act` is constrained to `false`, and `/safety/arm` returns `SAFETY_LOCKED`. The rails below are specified now so that Phase 4 cannot ship without them. They live in `config/safety.yaml` and `services/actions`.

1. **Single choke point.** Only `titan-actions` may call `SendInput`, `vgamepad`, or adapter `execute()`. Lint rule (`tools/lint-imports`): imports of `ctypes.windll.user32.SendInput`, `pyautogui`, `vgamepad`, or `pydirectinput` outside `services/actions` fail CI.
2. **Default disarmed.** Each session starts disarmed. Arming requires the user to click "Arm AI control" (typed confirmation), the session mode to be `assist` or `autonomous`, the game manifest to allow control, `anti_cheat: false`, and no multiplayer mode detected.
3. **Kill switch** `Ctrl+Shift+F12` (configurable) is registered three ways: Electron `globalShortcut`, a low-level keyboard hook in `titan-actions`, and the UI button. A kill: (a) stops the action executor, (b) **releases all held keys and buttons and centres all axes** (tracked held-state table), (c) resets the virtual gamepad, (d) cancels pending proposals, (e) sets `SafetyState.killed=true`, and (f) publishes `safety.kill`. Hotkey to released inputs takes 50 ms or less. Resume needs explicit user action and re-arming.
4. **Watchdog.** `titan-actions` needs a heartbeat from the orchestrator every 1 s while armed. Two missed heartbeats trigger an automatic kill (`source:"watchdog"`).
5. **Human override.** A Raw Input listener watches physical devices. Any real keyboard, mouse, or controller input (injected events carry `LLMHF_INJECTED`/`LLKHF_INJECTED` and are ignored) sets `control_owner="human"` for 3 s after the last input. All AI actions are suppressed and held inputs released. The UI shows "HUMAN CONTROL".
6. **Foreground lock.** Inject only when the foreground window's process ID equals the game's process ID. Otherwise drop the action and emit `action.executed{ok:false,error:"not_foreground"}`.
7. **Rate limits** (token buckets): key presses 20/s, mouse moves 60/s, clicks 5/s, axis updates 60/s, menu macros 1 per 2 s, and `irreversible` actions 1 per 10 s.
8. **Policy gating by `action_class`:** `continuous` and `discrete` are approved by the Director if risk is `low` or `medium`. `irreversible` (KSP decouple or stage while landed, quicksave overwrite, purchases, job cancel) requires **user approval** in the UI with a 10 s timeout that defaults to deny. `menu` macros are allowlisted per adapter.
9. **Allowlist:** only `action_id`s present in the adapter's `action_space()` are accepted. Unknown IDs are rejected and audited.
10. **Audit:** every proposal, decision, and execution is an event (`category="safety"` for denials and kills) and is kept indefinitely.

### 6.10 Session end and memory writes (Phase 1 learning loop)
On `stop`: (1) agents terminate, (2) recording finalizes, (3) Celery `session.summarize` (P4 priority, `llm_batch`) builds the **SessionReport**:
```json
{ "session_id": "...", "duration_ms": 0, "outcome": "partial",
  "missions": [{ "mission_id": "...", "title": "Reach orbit", "status": "failed", "reason": "Ran out of fuel at Pe 41 km" }],
  "success_log": [{ "t_session_ms": 0, "text": "", "event_ids": [] }],
  "failure_log": [{ "t_session_ms": 0, "text": "", "event_ids": [], "root_cause": "" }],
  "discoveries": [{ "text": "", "bb_ref": {} }],
  "updated_strategies": [{ "strategy_id": null, "title": "", "change": "new|reinforced|weakened" }],
  "lessons": [{ "lesson": "", "applies_when": "" }],
  "agent_scores": [{ "instance_id": "...", "role": "", "tasks_ok": 0, "tasks_failed": 0, "avg_eval": 0.0, "utterances": 0 }],
  "stats": { "events": 0, "utterances": 0, "tokens": 0, "llm_p95_ms": 0, "avg_fps": 0.0 } }
```
(4) Memory writes: one `episodic/summary` memory per mission, a `failure` memory per failure-log item (importance 0.7 or more), `long_term/discovery` memories for discoveries with confidence 0.6 or more, `strategic/lesson` memories for lessons, strategy rows created (`candidate`) or `times_used`/`times_succeeded` updated, and `risk_entries.occurrences` incremented for fired risk rules. (5) Chroma upserts through the `embed` queue. Memories from earlier sessions are retrieved in the next session's agent context (Section 2.11), which closes the Phase 1 learning loop.

---

## 7. Telemetry integration (Phase 1 games)

### 7.1 Pipeline
```
 adapter.frames() @ native rate (KSP 20 Hz, SCS 20 Hz)
   -> raw frame -> writer: telemetry/frames-NNNN.ndjson.zst (raw + normalized, rotated every 5 min)
   -> adapter.normalize() -> TelemetryFrame (validated in dev/test; validation sampled at 1% in prod)
   -> rule engine + adapter.detect_events() -> GameEvent[] -> XADD events (+ marker if rule says so)
   -> rate limiter -> XADD telemetry @ 10 Hz
   -> 1 Hz sampler -> telemetry_samples (batched insert every 5 s)
```
The host reconnects with backoff (1 s, 2 s, 5 s, then every 5 s) whenever the adapter raises `GameNotConnected`. It emits `system.telemetry.disconnected` / `system.telemetry.connected` events. Pause (`paused=true`) keeps frames flowing at 1 Hz and suppresses game-event rules except `game.paused` / `game.resumed`.

### 7.2 Normalized telemetry schema (`titan.telemetry/1`)
Units are SI everywhere (m, m/s, kg, L, Pa, degrees C, s). Angles are degrees. Ratios are 0 to 1. Missing values are `null` and never fabricated.
```ts
type TelemetryFrame = {
  schema: "titan.telemetry/1";
  session_id: UUID; game: string;              // 'ksp' | 'ets2' | 'ats' | ...
  adapter_version: string;
  seq: number;                                 // per session, monotonic
  t_mono_ns: number; t_session_ms: number;
  t_game_s: number | null;                     // KSP UT seconds; SCS game time in seconds
  paused: boolean;
  scene: string;                               // ksp: flight|map|vab|sph|space_center|tracking|menu ; scs: driving|menu|loading|map
  domain: "space" | "ground_vehicle" | "aircraft" | "naval" | "strategy" | "other";
  vehicle: {
    name: string | null; kind: string | null;  // 'rocket','truck'
    position: { frame: string; x: number; y: number; z: number } | null;   // ksp: body-centred; scs: world metres
    geo: { lat_deg: number; lon_deg: number; alt_m: number } | null;
    attitude: { heading_deg: number; pitch_deg: number; roll_deg: number } | null;
    velocity: { speed_mps: number; vertical_mps: number | null; horizontal_mps: number | null } | null;
    accel_g: number | null;
    controls: { throttle: number | null; brake: number | null; steer: number | null; clutch: number | null;
                gear: number | null; sas: boolean | null; rcs: boolean | null; parking_brake: boolean | null;
                cruise_control_mps: number | null; lights: string | null } | null;
    engine: { running: boolean | null; rpm: number | null; temp_c: number | null; max_temp_ratio: number | null } | null;
    damage: { overall: number | null; parts: Record<string, number> } | null;   // 0 = pristine, 1 = destroyed
    situation: string | null;                  // ksp: pre_launch|flying|sub_orbital|orbiting|escaping|landed|splashed|docked
    stage: { current: number; total: number | null; dv_ms: number | null } | null;
    orbit: { body: string; apoapsis_m: number; periapsis_m: number; inclination_deg: number; eccentricity: number;
             period_s: number | null; time_to_apoapsis_s: number | null; time_to_periapsis_s: number | null;
             time_to_soi_change_s: number | null } | null;
  };
  resources: Array<{ id: string; name: string; amount: number; capacity: number; unit: string;
                     scope: "vehicle" | "stage" | "trailer" }>;
  environment: { body: string | null; atmosphere_density: number | null; dynamic_pressure_pa: number | null;
                 static_pressure_pa: number | null; speed_limit_mps: number | null; weather: string | null;
                 local_time: string | null } | null;
  job: { active: boolean; cargo: string | null; mass_kg: number | null; source: string | null; destination: string | null;
         income: number | null; currency: string | null; deadline_game_s: number | null;
         nav_distance_m: number | null; nav_time_s: number | null; trailer_attached: boolean | null;
         cargo_damage: number | null } | null;
  economy: { funds: number | null; science: number | null; reputation: number | null; currency: string | null } | null;
  game_specific: Record<string, unknown>;      // adapter-defined, documented in the game package README
};
type TelemetryFrameUI = Omit<TelemetryFrame, "game_specific">;
```
Fuel range and similar derived values are computed in adapter tools or `world_state_summary()`, never stored as raw telemetry.

### 7.3 Kerbal Space Program (KSP 1.12.x) via kRPC
**Setup (adapter `check_integration` / `install_integration`):**
- Require KSP 1.12.x (`buildid` from the Steam manifest or `buildID64.txt`). KSP 2 is unsupported.
- Require the kRPC mod (version pinned in `third_party/manifest.yaml`, 0.5.x line; M5 verifies it against 1.12.5) at `<KSP>/GameData/kRPC/`. Install copies the pinned, hash-verified zip contents after user consent. Never overwrite another version silently; report `incompatible`.
- Write `<KSP>/GameData/kRPC/PluginData/settings.cfg` with `autoStartServers = True`, address `127.0.0.1`, RPC port `50000`, stream port `50001`, and `autoAcceptConnections = True`, after showing the user what changes.
- Python client: `krpc` (same version line). Connect with `krpc.connect(name="Titan", address="127.0.0.1", rpc_port=50000, stream_port=50001)`.

**Sampling plan:**
| Data | Method | Rate |
|---|---|---|
| Scene | `conn.krpc.current_game_scene` | 2 Hz |
| Active vessel identity | `space_center.active_vessel` (re-create all streams on change) | 2 Hz |
| `flight(body.reference_frame)`: `mean_altitude`, `surface_altitude`, `speed`, `vertical_speed`, `horizontal_speed`, `heading`, `pitch`, `roll`, `g_force`, `dynamic_pressure`, `static_pressure`, `atmosphere_density`, `latitude`, `longitude` | kRPC **streams** (`conn.add_stream`), `stream.rate = 20` | 20 Hz |
| `orbit`: `apoapsis_altitude`, `periapsis_altitude`, `inclination` (rad to deg), `eccentricity`, `period`, `time_to_apoapsis`, `time_to_periapsis`, `time_to_soi_change`, `body.name` | streams | 5 Hz |
| `control`: `throttle`, `sas`, `rcs`, `current_stage`, `gear`, `brakes` | streams | 10 Hz |
| `situation`, `met`, `space_center.ut` | streams | 5 Hz |
| Resources: `vessel.resources` (vehicle) and `vessel.resources_in_decouple_stage(current_stage - 1)` (stage) for LiquidFuel, Oxidizer, SolidFuel, MonoPropellant, ElectricCharge, XenonGas | polled | 2 Hz |
| Part temperatures: the 10 parts with the highest `temperature / max_temperature` (full part scan every 5 s, the top 10 tracked at 1 Hz) | polled | 1 Hz |
| Funds, science, reputation (career only) | `space_center.funds`, `.science`, `.reputation` | 0.2 Hz |

**Mapping notes:** `vehicle.position` uses frame `body:<name>` (`vessel.position(body.reference_frame)`). `vehicle.stage.dv_ms` is computed by the adapter tool `ksp.stage_dv` (Tsiolkovsky with engine ISP from `vessel.parts.engines` and the stage masses), at 1 Hz, and marked `null` when uncomputable. `engine.max_temp_ratio` is the max over the tracked parts. `game_specific` contains `{met_s, ut_s, vessel_type, part_count, crew_count, target_name}`.

**Robustness:** every kRPC call is wrapped. `RPCError` with "No active vessel" means scene not `flight`, so the frame is emitted with `vehicle` fields `null`. Dropped TCP leads to reconnect. The kRPC client runs on a dedicated thread (blocking API) feeding an `asyncio.Queue`.

**KSP events (`games/ksp/events.yaml`):**
| Event type | Rule | Severity / salience | Marker |
|---|---|---|---|
| `ksp.scene_changed` | `scene` changed | info / 0.2 | none |
| `ksp.launch` | `situation` `pre_launch` to `flying` or `sub_orbital` | notice / 0.8 | highlight |
| `ksp.staging` | `stage.current` decreased | info / 0.5 | none |
| `ksp.max_q` | peak of `dynamic_pressure_pa` over 5000, 3 s window | notice / 0.7 | highlight |
| `ksp.apoapsis_target` | `orbit.apoapsis_m` crossed above the mission target | notice / 0.6 | none |
| `ksp.orbit_achieved` | `situation=orbiting` and `periapsis_m` over the body's atmosphere height (Kerbin 70 km) | notice / 0.9 | achievement |
| `ksp.soi_changed` | `orbit.body` changed | notice / 0.8 | achievement |
| `ksp.stage_fuel_depleted` | stage LiquidFuel+Oxidizer+SolidFuel ratio under 0.01 while throttle over 0 | warning / 0.6 | none |
| `ksp.overheat_warning` | `engine.max_temp_ratio` over 0.85 for 2 s | warning / 0.7 | tension |
| `ksp.high_g` | `accel_g` over 8 for 1 s | warning / 0.6 | tension |
| `ksp.landed` | `situation` to `landed` or `splashed` with vertical speed magnitude under 10 m/s | notice / 0.9 | achievement |
| `ksp.vessel_destroyed` | vessel lost (active vessel invalid or replaced while the previous situation was flying and part count dropped by 50% or more within 1 s) | critical / 1.0 | failure |
| `ksp.low_power` | ElectricCharge ratio under 0.1 | warning / 0.5 | none |

### 7.4 GameEvent schema
```ts
type GameEvent = {
  id: UUID; session_id: UUID; seq: number;
  type: string;                                // '<game>.<name>' or 'vehicle.<name>' for shared rules
  category: "game" | "agent" | "system" | "user" | "safety" | "recording";
  severity: "debug" | "info" | "notice" | "warning" | "critical";
  salience: number;                            // 0..1, drives commentary urgency and highlight scoring
  source: string;                              // 'rule:ksp.max_q' | 'adapter:scs' | 'capture'
  t_mono_ns: number; t_session_ms: number; occurred_at: string;
  frame_seq: number | null;
  payload: Record<string, unknown>;
  marker?: { kind: MarkerKind; duration_ms: number };
};
```

### 7.5 Declarative event rule DSL
Rules live in each game package's `events.yaml`. The engine (`services/telemetry/rules.py`) evaluates them on every normalized frame. There is no `eval()`: only the operators below. Paths are dotted into `TelemetryFrame` (array elements by `resources[id=LiquidFuel].amount`).
```yaml
- id: vehicle.fuel_low                    # shared by ETS2/ATS via scs-common
  type: vehicle.fuel_low
  when:
    all:
      - { path: "resources[id=fuel].ratio", op: "<", value: 0.15 }   # ratio = amount/capacity (virtual field)
      - { path: "paused", op: "==", value: false }
  for_s: 5                                 # condition must hold continuously
  cooldown_s: 600                          # re-arm only after the condition clears and cooldown passes
  severity: warning
  salience: 0.6
  payload:
    fuel_l: "resources[id=fuel].amount"
    nav_distance_remaining_km: { path: "job.nav_distance_m", scale: 0.001 }
- id: ksp.max_q
  type: ksp.max_q
  when: { peak: { path: "environment.dynamic_pressure_pa", min_value: 5000, window_s: 3 } }
  severity: notice
  salience: 0.7
  marker: { kind: highlight, duration_ms: 8000 }
  payload: { dynamic_pressure_pa: "$peak", altitude_m: "vehicle.geo.alt_m" }
```
**Operators:** `== != < <= > >=`, `changed`, `changed_to`, `changed_from`, `increased_by`, `decreased_by` (with `within_s`), `crossed_above`, `crossed_below`, `peak` / `trough` (local extremum after `window_s`), `is_null`. **Combinators:** `all`, `any`, `not`. **Modifiers:** `for_s`, `cooldown_s`, `once_per_session`, `only_in_scene: [..]`. Missions' `success_criteria` and risks' `trigger_conditions` use the same predicate objects. Rules are tested with golden fixture replays (Section 9.2).

### 7.6 Euro Truck Simulator 2 and American Truck Simulator via the SCS Telemetry SDK
**Setup:**
- The SCS SDK is a C API loaded from DLLs in `<game>/bin/win_x64/plugins/`. Titan installs the community **scs-sdk-plugin** (RenCloud) DLL as `scs-telemetry.dll`, version and SHA-256 pinned in `third_party/manifest.yaml`. M4 confirms its license and current revision.
- On the first game start after install, the game shows an "Advanced SDK features" dialog. The integration UI tells the user to accept it.
- The plugin exposes a named shared-memory block `Local\SCSTelemetry`. Python opens it read-only: `mmap.mmap(-1, SIZE, tagname="Local\\SCSTelemetry", access=mmap.ACCESS_READ)`. If it is missing, the status is `missing`, or `installed` while the game is not running.

**Layout parser:** `games/scs-common/titan_game_scs/layouts/rencloud-<ver>.yaml` lists every field as `{name, offset, type (u8|bool|i32|u32|u64|f32|f64|char[N]|f32[3]...), unit}`. It is derived from the plugin's published C/C# shared-memory struct for that exact version. At connect, the adapter reads the header fields (`sdkActive`, `paused`, plugin revision, game id 1=ETS2 / 2=ATS, game version) and **refuses to run** (status `incompatible`) if the revision has no layout file. Unpacking uses one precompiled `struct.Struct` per layout. Polling is at 20 Hz, and a frame is emitted only when the SCS timestamp field advances, or every 1 s while paused.

**Field mapping (a subset is normative; full mapping lives in the layout file):**
| SCS field (plugin) | Normalized path | Conversion |
|---|---|---|
| `truck.speed` (m/s) | `vehicle.velocity.speed_mps` | abs |
| `truck.engineRpm` | `vehicle.engine.rpm` | none |
| `truck.gear` / `displayedGear` | `vehicle.controls.gear` | none |
| `truck.fuel`, `fuelCapacity` | `resources[id=fuel]` (L, scope vehicle) | none |
| `truck.fuelAvgConsumption` (L/km) | `game_specific.fuel_avg_l_per_km` | none |
| `truck.cruiseControlSpeed`, `cruiseControl` | `vehicle.controls.cruise_control_mps` | `null` when off |
| `truck.userThrottle/Brake/Steer/Clutch` | `vehicle.controls.*` | steer clamped to -1..1 |
| `truck.parkBrake` | `vehicle.controls.parking_brake` | none |
| `truck.wearEngine/Transmission/Cabin/Chassis/Wheels` | `vehicle.damage.parts.*`, `overall` = max | 0..1 |
| `truck.waterTemperature`, `oilTemperature` | `vehicle.engine.temp_c` (water) | none |
| `truck.worldPlacement` (x,y,z, heading 0..1, pitch, roll) | `vehicle.position{frame:"scs_world"}`, `attitude` | heading x 360 |
| `navigation.speedLimit` (m/s) | `environment.speed_limit_mps` | `null` if 0 |
| `navigation.navigationDistance` (m), `navigationTime` (s) | `job.nav_distance_m`, `job.nav_time_s` | none |
| `job.cargo`, `cargoMass`, `cityDst`, `compDst`, `citySrc`, `compSrc`, `income`, `deliveryTime` | `job.*` | currency EUR (ETS2) / USD (ATS) |
| `trailer[0].attached`, `trailer[0].wearCargo` | `job.trailer_attached`, `job.cargo_damage` | none |
| `common.gameTime` (minutes) | `t_game_s` | x 60 |
| `paused` | `paused` | none |
| Plugin gameplay-event fields (job delivered or cancelled, player fined, tollgate paid, ferry, train, refuel paid) | events `scs.job.delivered`, `scs.job.cancelled`, `scs.player.fined`, `scs.player.tollgate`, `scs.player.ferry`, `scs.player.train`, `scs.player.refuel` | edge-detected flags. Payload carries the amounts and offence |

ATS uses the same layout. The `ats` manifest only changes `currency`, detection, and display units (the UI converts to mph or gallons if the user picks imperial; storage stays SI).

**SCS events (shared `scs-common/events.yaml` plus per-game overrides):**
| Event type | Rule | Severity / salience | Marker |
|---|---|---|---|
| `scs.job.started` | `job.active` false to true | notice / 0.5 | chapter |
| `scs.job.delivered` | plugin flag | notice / 0.9 | achievement |
| `scs.job.cancelled` | plugin flag | warning / 0.7 | failure |
| `scs.player.fined` | plugin flag | warning / 0.8 | funny |
| `vehicle.collision` | `damage.overall` increased by 0.02 or more within 0.5 s, or speed decreased by 8 m/s or more within 0.3 s | critical / 0.95 | failure |
| `vehicle.speeding` | `speed > speed_limit x 1.1 + 2` for 10 s | notice / 0.4 (cooldown 300 s) | none |
| `vehicle.fuel_low` | Section 7.5 | warning / 0.6 | tension |
| `scs.player.refuel` | plugin flag, or fuel increased by 5 L or more while stopped | info / 0.4 | none |
| `vehicle.cargo_damage` | `job.cargo_damage` crossed above 0.05, 0.15, 0.3 | warning / 0.7 | failure |
| `scs.ferry` / `scs.train` | plugin flag | notice / 0.6 | chapter |

### 7.7 Controls ingestion (Phase 1, read-only)
- KSP: parse `<KSP>/settings.cfg` key blocks (e.g. `STAGE { primary = Space }`) into `control_bindings` with `source=config_file`. Fallback: `controls_default.yaml`.
- SCS: parse `profiles/<id>/controls.sii` `config_lines` `mix` entries into bindings. Profile IDs are hex-encoded names; the UI lets the user pick a profile.
- `action_class` comes from the adapter's `controls_default.yaml` (for example `ksp.stage` is `irreversible` while landed, otherwise `discrete`; `truck.cruise_control` is `discrete`).

---

## 8. Phased implementation plan

### 8.1 Phase overview and dependencies
```
P1 Foundation --+--> P2 Research --> P3 Agent Factory --+
                |                                        +--> P4 Gameplay Autonomy
                +--> P5 Commentary (needs P1; better with P3 personas)
                `--> P6 Content Studio (needs P1 recordings/markers) --> P7 YouTube --> P8 Self-Improvement
P8 also consumes P2-P5 data. P4 needs P2 controls and P3 teams; it can start from P1 + hand-made controls.
```

### 8.2 Phase 1: Foundation MVP

Each task becomes a branch and a PR (see "How coding workers use this spec"). Tests named per task are required for the PR to merge.

**M0: Repository and toolchain**
| Task | Work |
|---|---|
| M0.T1 | Scaffold the monorepo exactly as in Section 3: pnpm and uv workspaces, root configs, `.gitignore`, `.gitattributes` (LFS rules) |
| M0.T2 | CI workflows (Section 9.3) with placeholder test suites. Branch protection documented in `docs/dev-setup.md` |
| M0.T3 | `titan-core`: config loader, structlog setup, UUIDv7, clock, error codes |
| M0.T4 | `titan_core.protocol` models for envelope, payloads, telemetry, WS, events. `tools/codegen.py` produces `schemas/*.json` and `packages/ts/protocol` (types plus zod). `codegen-check` workflow |
| M0.T5 | ADRs 0001 to 0019 for D1 to D19. `docs/dev-setup.md`. PR template. CODEOWNERS |
| M0.T6 | `third_party/manifest.yaml` and `tools/fetch-third-party.py` (SHA-256 verified). Starts with PostgreSQL 16, FFmpeg 7, PresentMon, kRPC, scs-sdk-plugin |

*Acceptance:* a fresh clone runs `pnpm i && uv sync && pnpm codegen && pnpm test` green on Windows and Ubuntu. CI is green. Changing a protocol model without running codegen fails CI. *Tests:* unit tests for ids, clock, and config layering. A codegen round-trip test (Pydantic to JSON Schema validates sample payloads in both Python and zod).

**M1: Platform services and supervisor**
| Task | Work |
|---|---|
| M1.T1 | Portable Postgres management: initdb on first run, `pg_ctl` start and stop, random superuser password in Credential Manager, port 54329, `listen_addresses='127.0.0.1'`, `unix_socket_directories=''`, and a `pg_hba.conf` with only `host all all 127.0.0.1/32 scram-sha-256`. `pg_ctl` is required on Windows (it drops administrator rights; `postgres` refuses to run elevated). A server already running on the data directory is adopted |
| M1.T2 | Memurai or Redis health check with `requirepass` (a server that also accepts anonymous clients reports `degraded`). Chroma server process on loopback only: Chroma 1.x removed built-in auth (R16) |
| M1.T3 | Supervisor: process table from config, start order, restart backoff and circuit breaker, internal health endpoint, Windows job object so children die with the parent |
| M1.T4 | FastAPI skeleton: `/health`, `/system/status`, bearer auth, problem+json handlers, WS gateway skeleton with auth and `system.metrics` |
| M1.T5 | Electron shell: spawns the supervisor with the launch token, boot splash showing service states, menu skeleton, kill-switch shortcut wired to `/safety/kill` (no-op state in P1) |
| M1.T6 | Metrics: psutil, NVML (`nvidia-ml-py`), PresentMon console process tracking the game PID, published at 1 Hz to the telemetry bar |

*Acceptance:* a cold start brings all services to healthy in under 20 s on the reference PC. Killing any child process gets it restarted in under 10 s with an event logged. Quitting the app leaves zero Titan processes (verified with `tasklist`). The telemetry bar shows live CPU, GPU, RAM, and FPS (FPS shows `n/a` with no game). *Tests:* supervisor unit tests with fake processes. A Windows CI job that starts Postgres and the API and checks `/system/status`. HIL checklist entry for orphan processes. The CI job is `tests/integration/test_supervisor_e2e.py` (Ubuntu and Windows): it runs the real supervisor with managed Postgres, kills children, and checks that nothing is left after shutdown; on Windows it also uses the real Credential Manager and checks that a hard kill of the supervisor leaves nothing behind (job object). GPU, FPS and the reference-PC timing need the HIL checklist.

**M2: Data layer and configuration**
| Task | Work |
|---|---|
| M2.T1 | SQLAlchemy models and the first Alembic migration for every table in Section 4.2 |
| M2.T2 | Async repositories. Transaction helper |
| M2.T3 | Layered config (Section 9.5). `/settings` GET and PATCH with versioning |
| M2.T4 | Seed data: games (ksp, ets2, ats from manifests), personas, and default teams (Appendix A) |
| M2.T5 | StreamPersister (bus and events into Postgres, batched every 250 ms or 500 rows, idempotent) |

*Acceptance:* `alembic upgrade head` then `downgrade base` runs clean. The constraints hold: only one live session, `approval_required`, `p1_no_actions`, one director per team. The persister writes each envelope exactly once under duplicate delivery and survives a Postgres restart without loss (Redis pending entries are retried). *Tests:* migration tests in CI (Postgres service container). Constraint tests. Hypothesis property test for the persister's idempotency.

**M3: Model provider, scheduler, embeddings, Resource Guard**
| Task | Work |
|---|---|
| M3.T1 | `ModelProvider` protocol plus Ollama, OpenAI-compatible, and Fake providers |
| M3.T2 | `models.yaml` routing, profiles, and fallbacks. `/models`, `/models/routes`, `/models/pull` (Celery job with progress) |
| M3.T3 | LLM Scheduler (priorities, reserved slot, pre-emption, deadlines, token budget) with `llm_calls` logging |
| M3.T4 | SentenceTransformers embedder. `titan-memory` `VectorStore` interface and Chroma implementation with collections from Section 4.3 |
| M3.T5 | Resource Guard ladder driven by `titan:sys:metrics` |

*Acceptance:* streaming works end to end with TTFT recorded. A P1 request pre-empts P3 within 100 ms (FakeProvider timing test). A missing model falls back with a `system.notice`. Ollama down gives `DEPENDENCY_UNAVAILABLE`. Synthetic FPS drops move the guard L0 to L3 and back with hysteresis. *Tests:* unit tests with FakeProvider. Recorded-HTTP tests (respx) for Ollama request and response shapes. HIL: real Ollama TTFT on the reference PC.

**M4: Game discovery and adapter SDK**
| Task | Work |
|---|---|
| M4.T1 | `titan-sdk-games`: manifest model, `GameAdapter` ABC, entry-point loader, adapter test harness (feeds fixtures) |
| M4.T2 | Store scanners: Steam (VDF/ACF parser), Epic, GOG, standalone |
| M4.T3 | KSP, ETS2, ATS packages: manifests, `check_integration`, `install_integration` (hash-verified, reversible, consent required), launch |
| M4.T4 | Controls parsers (KSP `settings.cfg`, SCS `controls.sii`) into `control_bindings` |
| M4.T5 | Games UI: discovery, integration installer with instructions, launch button |

*Acceptance:* on the reference PC with all three games, a scan finds them with correct paths and versions in under 5 s. Integration install is idempotent, refuses on hash mismatch, and can be undone. Adding a dummy game package in tests (`games/_testgame`) makes it appear in `/games` with **no core code change** (enforced by a test that installs the package into a temp venv). *Tests:* fake Steam library and registry fixtures (Windows CI job). Parser unit tests with sample `settings.cfg` and `controls.sii`.

**M5: Telemetry pipeline**
| Task | Work |
|---|---|
| M5.T1 | `titan-telemetry` host: adapter loading, frame loop, writer (zstd chunks and 1 Hz samples), replay mode (1x, 2x, 10x) |
| M5.T2 | KSP kRPC adapter (Section 7.3) including reconnect, scene handling, and vessel switching |
| M5.T3 | SCS shared-memory adapter (Section 7.6) with the layout file and revision check, shared by ETS2 and ATS |
| M5.T4 | Rule engine (Section 7.5) and `events.yaml` for each game |
| M5.T5 | `tools/record-fixture.py` plus fixtures: KSP launch-to-orbit, KSP crash, ETS2 delivery with a fine, ATS short haul with low fuel |
| M5.T6 | WS `telemetry` and `events` channels. UI event log and telemetry charts |

*Acceptance:* latency budgets in Section 2.6 met (game to stream p95 under 50 ms; frame to UI p95 under 250 ms). Replaying each fixture produces a byte-identical event sequence against golden files. The adapter survives game restart, pause, menus, and scene changes without restarting the process. Telemetry alone costs 1% or less of game FPS. *Tests:* golden replay tests in CI (no game needed). A synthetic SCS shared-memory writer test on the Windows CI job. kRPC adapter tests against a fake kRPC server stub. HIL: live runs of all three games.

**M6: Multi-agent core**
| Task | Work |
|---|---|
| M6.T1 | Bus client, router, envelope validation, TTL and priority inboxes |
| M6.T2 | `BlackboardService`: CAS, permissions, TTL, conflict detection, history, Redis cache rebuild |
| M6.T3 | `AgentRuntime` LangGraph, context builder with token budget, tool registry (adapter tools plus core `bb.read`, `bb.write`, `memory.search`, `knowledge.search`), Postgres checkpointer |
| M6.T4 | Director graph and task lifecycle (Section 6.5) |
| M6.T5 | Floor Manager (Section 6.7) with anti-repetition and grounding checks |
| M6.T6 | Personas and team templates (Appendix A). Session controller starts the orchestrator |
| M6.T7 | WorldStateUpdater and EventRouter |

*Acceptance:* with FakeProvider replaying the KSP launch fixture, task lifecycles follow Section 6.5 exactly (state-transition assertions). There is never more than one active `say` stream (invariant checked over 1,000 randomized runs). Killing the orchestrator mid-session leads to resume within 10 s with the blackboard intact and no duplicated tasks. With real Ollama on the reference PC, event to first token p50 is 1.5 s or less. *Tests:* unit tests for each service. Hypothesis tests for blackboard CAS and floor invariants. An integration test spanning API, orchestrator, telemetry replay, and FakeProvider (Linux CI).

**M7: Operations Center UI**
| Task | Work |
|---|---|
| M7.T1 | Layout and menus from Section 2.13. Resizable panels persisted to `settings` |
| M7.T2 | Agents panel: streaming chat, persona chips, mute, user chat box with `@persona` autocomplete |
| M7.T3 | Webcam panel: MJPEG preview, mic meter, face box, per-track recording state |
| M7.T4 | Telemetry bar and charts. Virtualized event log with filters and click-to-marker |
| M7.T5 | Inspectors (blackboard, messages, tasks) and the Director report view |
| M7.T6 | Session flows: new, start, pause, stop, replay, and the report view |

*Acceptance:* the Playwright-Electron e2e test in replay mode creates a session, starts it, sees chat streaming and events, stops it, and opens the report. The renderer stays at 55 fps or more with 10 Hz telemetry and active chat (Chrome performance trace). Menus are keyboard-navigable and text contrast meets WCAG AA. *Tests:* component tests (Vitest and Testing Library), e2e tests on the Windows CI job.

**M8: Capture and recording**
| Task | Work |
|---|---|
| M8.T1 | OBS client: provision profile and scene collection, start and stop, status via `GetRecordStatus` and `GetStats`, reconnect |
| M8.T2 | Webcam FFmpeg pipeline, MJPEG preview server, device enumeration |
| M8.T3 | Recording manifest, track rows, sync offsets, markers (`Ctrl+M` and rule markers) |
| M8.T4 | Finalization `media` job: remux, split audio tracks, checksums |
| M8.T5 | Disk guard. Failure handling: OBS disconnects mid-recording (event, reconnect, recording continues in OBS), webcam unplugged (track marked, session continues) |

*Acceptance:* a 60-minute 1080p60 recording has every track present. Drift is 40 ms or less (clap test: a hand clap seen on the webcam and heard on the mic, compared at start and end). Dropped frames are under 0.1%. Rule markers land within 1 frame of the event time. Works whether OBS was started before or after Titan. *Tests:* OBS client tests against a mock obs-websocket server. FFmpeg command builder unit tests. HIL clap test.

**M9: Memory database and learning loop**
| Task | Work |
|---|---|
| M9.T1 | Memory service: write, retrieve, scoring, short-term expiry |
| M9.T2 | Session-end pipeline (Section 6.10): report, memory writes, strategy and risk updates |
| M9.T3 | Retrieval into agent context, plus a "reference prior episodes" slot in the commentary prompt |
| M9.T4 | Memory Browser UI. Knowledge add and search |
| M9.T5 | `titan memory reindex` command and endpoint |

*Acceptance:* a second session of the same fixture has prior-session memories in agent context (FakeProvider assertion), and on HIL at least one utterance references the earlier episode. Reindex rebuilds identical counts. Deleting a memory removes it from Chroma. *Tests:* memory scoring unit tests. An end-to-end integration test running two replay sessions.

**M10: Hardening and Phase 1 exit**
| Task | Work |
|---|---|
| M10.T1 | Chaos tests: kill each process type during a live replay session and verify recovery |
| M10.T2 | 2-hour soak per game on the reference PC (HIL) |
| M10.T3 | Performance verification and tuning. Calibrate Resource Guard thresholds on real FPS data |
| M10.T4 | NSIS installer, first-run wizard (Ollama, OBS, Memurai, model pull, integrations), uninstall, diagnostics bundle |
| M10.T5 | User guide, game-adapter guide, runbooks |

**Phase 1 exit criteria (all required):**
1. On a clean reference PC, a user installs Titan, completes the wizard, launches KSP, ETS2, or ATS from Titan, and sees agents discussing the game using live telemetry, with the Agents panel, webcam panel, telemetry bar, and event log all live.
2. All Section 1.6 targets are met for each game in a 2-hour soak.
3. The session is recorded with separate gameplay, webcam, mic, and game-audio tracks, plus markers, and a session report is written to memory.
4. A second session references the first.
5. No input is ever sent to the game (verified by an audit test and code review of the import lint).
6. CI is green, and the HIL checklist is fully signed off and committed.

### 8.3 Phases 2 to 8 (milestone level)

**Phase 2: Autonomous game research** (depends on P1)
- R1 Source connectors: MediaWiki API (wikis), Steam Web API (news and patch notes), Steam guides and forums (HTML, robots.txt honoured, 1 request/s per domain, cached), Reddit through the official API with the user's own credentials, official docs, developer blogs, mod docs. YouTube is limited to **official API metadata plus captions the user has rights to, or local files the user provides**. No transcript scraping.
- R2 Local analysis: config, keybind, save, mission, and mod files through adapter parsers.
- R3 Extraction: chunk, then LLM structured extraction (JSON schema) into knowledge, controls, risks, and strategies with citations (`source_refs`), then dedupe by `content_hash` and merge confidence.
- R4 Knowledge graph: Postgres tables `kg_nodes(id, game_id, kind, name, props)` and `kg_edges(src, dst, rel, props)` (ADR: no separate graph database).
- R5 Game Knowledge Report: UI and markdown export.
- **Exit:** reports for KSP, ETS2, and ATS. Every entry cites a source. 80% or more of extracted default controls match the hand-made ground truth. Research runs as P4-priority jobs only when no session is live.

**Phase 3: Agent Factory** (depends on P2)
- F1 Role inference: from the knowledge base to a `TeamSpec` (JSON schema: roles, responsibilities, subscriptions, tools, topics).
- F2 Persona generation (name, traits, backstory, speaking style, colour), with a user review step.
- F3 Evaluation sandbox: run generated teams on replay fixtures and score them with a rubric (task success, grounding, diversity).
- F4 Director recruit and retire turned on (`director.can_spawn`). F5 Training Manager reports.
- **Exit:** generated teams for the three games score at least as well as the P1 hand-made teams on the replay rubric. A fourth game added through a manifest plus adapter gets a generated team with no core code change.

**Phase 4: Gameplay autonomy** (depends on P1, P2 controls, P3 teams)
- A1 `titan-actions` with every rail in Section 6.9, plus the HIL kill-switch test rig. A2 KSP control through the kRPC API (attitude, throttle, staging, autopilot primitives), with a training curriculum for KSP stages 1 to 6 from the source. A3 SCS control through a virtual gamepad with an assist-first ladder: lights, indicators, cruise control, then highway lane-keeping. A4 Vision: DXGI capture (`dxcam`) at 10 to 30 fps downscaled, OCR (Tesseract on CPU by default, EasyOCR optional), per-game YOLO UI and object models. A5 Action planning, path planning, and error recovery. A6 Practice and self-evaluation loops writing failure memories.
- **Exit:** KSP reaches a stable Kerbin orbit in 8 of 10 attempts with a reference craft. ETS2 completes a 50 km designated highway test route in assist mode with no more than 1 collision across 4 runs. The kill switch passes 100 of 100 HIL trials in under 50 ms. Fuzz tests show zero injected inputs outside the game window.

**Phase 5: AI commentary system** (depends on P1; uses P3 personas)
- C1 TTS: StyleTTS2 by default (MIT). XTTS-v2 is opt-in, with a non-commercial license warning. A separate `titan-voice` process plays audio into OBS track 3. C2 STT: faster-whisper on the mic, producing `user.say` (push-to-talk default). C3 Character system: banter, running jokes, cross-episode narrative arcs from memory. C4 Avatars: portraits via ComfyUI (SDXL or Flux-schnell, license-checked), live lightweight viseme animation, with LivePortrait/SadTalker renders done in post (P6) to keep the GPU free.
- **Exit:** TTS first audio is 800 ms or less after text. Repetition is 5% or less. Blind user rating of entertainment is 4/5 or higher across 10 clips.

**Phase 6: Content studio** (depends on P1 recordings, events, and markers)
- V1 OTIO timeline builder with the 8 tracks from the source. V2 Highlight detection (event salience, audio energy, chat intensity, markers) and chapter generation. V3 Captions (faster-whisper on mic and agent tracks). V4 Auto zoom and cuts (rule-based on events), B-roll from the session, music placement from a local library with user-supplied licences. V5 Rendering: FFmpeg by default, DaVinci Resolve through OTIO/FCPXML export, and the Resolve scripting API when Resolve Studio is detected. V6 Editor UI ("EDIT VIDEO").
- **Exit:** from a 2-hour session, a 12 to 20 minute draft renders in 30 minutes or less on the reference PC, and the user rates it as a usable rough cut in 4 of 5 trials.

**Phase 7: YouTube automation** (depends on P6)
- Y1 OAuth (Section 9.6), with each user's own Google Cloud project client. Y2 SEO generation (title, description with timestamps, tags, hashtags, pinned comment). Y3 Thumbnails: 5 to 20 candidates in the source styles through ComfyUI with a user pick. Y4 Resumable upload, `thumbnails.set`, scheduling, private-first default. Y5 Approval gate UI. Y6 Quota tracker.
- **Exit:** one-click publish after approval. Upload resumes after a network drop. Quota usage is shown before an upload is confirmed. Other platforms (Twitch, TikTok, Kick, X, Facebook) are follow-on adapters behind a `PublisherAdapter` interface.

**Phase 8: Self-improvement** (depends on P7; uses everything)
- S1 Analytics ingest (YouTube Analytics API) into `analytics_snapshots`. S2 Feature attribution: link retention dips and spikes to timeline segments and events. S3 Strategy promotion and deprecation from session outcomes. S4 Prompt and persona A/B tests with offline eval gates. S5 Highlight and thumbnail models retrained on observed CTR and retention.
- **Exit:** over 10 or more published videos, a measurable improvement versus baseline on at least two content metrics (CTR, average view percentage), and on mission success rate for the same tasks.

### 8.4 Risk register
| ID | Risk | Impact | Mitigation |
|---|---|---|---|
| R1 | **Anti-cheat and bans.** Input injection or process access in protected games (BattlEye, EAC: Arma, Squad, DCS multiplayer, War Thunder) | Account bans, legal | Manifest `anti_cheat: true` permanently disables the action layer. Titan never injects into or reads the memory of game processes. Only plugin and official APIs, screen capture, and OS input are used. The supervisor checks for known AC processes (`BEService.exe`, `EasyAntiCheat*.exe`) and blocks arming. Single-player only for P4 |
| R2 | **ToS and legality of research scraping** (Reddit, Fandom, YouTube, Steam) | Takedowns, blocked IPs | Official APIs first. Honour robots.txt, 1 request/s per domain, a descriptive User-Agent, and caching. No YouTube transcript scraping. Store citations and short excerpts, not full copies. Users supply their own API credentials |
| R3 | **YouTube API quota and audit.** The default quota is 10,000 units/day. An upload costs about 1,600 units (check current costs). Uploads from unaudited API projects are locked private | Can't publish publicly from API | Each user brings their own Google Cloud project and requests the audit (documented). Default privacy is `private` and the user flips it, which also keeps the human in control. The quota tracker blocks uploads that would exceed it |
| R4 | **GPU contention** between the game, LLM, NVENC, and later TTS and vision | Stutter, a bad viewer experience | Single-model residency, Resource Guard ladder, CPU embeddings, LLM concurrency of 2, game-first priority, post-session batch work, VRAM profiles, and a "max game priority" toggle |
| R5 | **Latency budgets missed** (commentary arrives after the moment) | Stale, boring commentary | Short outputs (80 tokens or fewer), a reserved P1 slot, stale-drop at 3 s, a pre-warmed model (`keep_alive`), a prompt-prefix cache (static persona prefix first), and smaller models for commentary |
| R6 | **Celery on Windows** (no prefork) | Worker hangs | `threads` and `solo` pools, one process per queue class, `acks_late`, supervisor restarts. ADR to switch to arq if instability persists |
| R7 | **Plugin and mod version drift** (kRPC versus KSP, SCS plugin versus game updates) | Telemetry breaks after updates | Pinned versions plus hashes. Revision checks refuse unknown layouts with a clear UI message. Fixture tests per version. `record-fixture` for fast re-validation |
| R8 | **OBS or obs-websocket changes** | Recording fails | Require OBS 30+ (bundled obs-websocket v5). Feature-detect via `GetVersion`. Mock-server contract tests |
| R9 | **Third-party licenses** (Memurai redistribution, Llama community license, XTTS CPML non-commercial, Flux-dev non-commercial, the SCS plugin license) | Can't ship or monetise | The installer never bundles restricted components; the wizard installs them with the user accepting their licenses. Default to permissive options (Qwen Apache-2.0 models, StyleTTS2 MIT, Flux-schnell Apache-2.0). License review checklist in M0/M10 |
| R10 | **Disk space and I/O** (4K60 recording is about 50 to 100 GB/h) | Recording failure | Disk guard, separate recording drive recommendation, CQP presets, remaining-time warnings |
| R11 | **LLM hallucination or unsafe humour** | Wrong facts, offensive content | Grounding rule and numeric post-check. Persona `avoid` lists. A local moderation pass (regex blocklist plus an optional small classifier) before `chat.final`. User mute and kill controls |
| R12 | **Prompt injection from research content** (P2+) | Agents misbehave | Research text is data, wrapped in delimited, quoted context and never in the system role. Tools are allowlisted per agent. The action layer ignores instructions from text and only accepts schema-valid proposals through policy |
| R13 | **Voice and likeness consent** (cloning, facecam) | Legal and ethical | Voice cloning only from the user's own recorded consent sample, stored locally. No celebrity voices or likenesses in personas |
| R14 | **ViGEmBus retirement** | No virtual gamepad on future Windows | API control first. vJoy as an alternative. SendInput fallback. ADR at P4 start |
| R15 | **Scope and complexity** | Phase 1 slips | Strict phase gates. Interfaces now, implementations later. Replay mode makes most work testable without games or a GPU |
| R16 | **Chroma has no authentication** (removed in Chroma 1.0) | Another local process could read or change the vector index | Bind `127.0.0.1` only, never `0.0.0.0`. Chroma holds derived data (embeddings of memories and knowledge that live in Postgres), so it can be rebuilt with `/memory/reindex`. Revisit if Chroma restores auth; a token proxy in front of it does not help while its own port is reachable locally |

---

## 9. Engineering standards

### 9.1 Code standards
- **Python 3.12.** `ruff` handles lint and format (rules `E,F,W,I,B,UP,SIM,ASYNC,S,PTH,RUF`, line length 110). `mypy --strict` on `packages/py/*` and `services/*`. Pydantic v2 at every boundary. Async by default: no blocking I/O on the event loop (`ASYNC` lint rules; use `anyio.to_thread.run_sync` for blocking libraries such as the kRPC client). No bare `except`. Errors are typed with `TitanError(code, detail)`. Logs use keyword fields, not f-strings.
- **TypeScript.** `strict: true`, `noUncheckedIndexedAccess`, ESLint (`typescript-eslint` strict-type-checked, `react-hooks`), Prettier. No `any` (use `unknown` plus zod). Feature-folder structure. Redux Toolkit slices plus RTK Query only (no ad-hoc fetch). WS messages are validated with the generated zod schemas in development builds.
- **Generated code** (`schemas/`, `packages/ts/protocol/src/generated/`) is committed, never edited by hand, and checked by CI.
- **Boundaries:** services talk only through REST, bus, or Celery, and never import each other. Shared code lives in `packages/`. An import-linter contract enforces this (`tools/lint-imports`), including the input-library ban from Section 6.9.
- **Commits and PRs:** Conventional Commits (`feat(telemetry): ...`). The PR title carries the task ID. Squash-merge to `main`. Semantic version tags `vX.Y.Z`. The protocol `schema` versions (`titan.msg/1`, `titan.telemetry/1`) bump only on breaking changes, with a migration ADR.

### 9.2 Testing
| Layer | Tools | Scope and gate |
|---|---|---|
| Unit | pytest, pytest-asyncio, Hypothesis, Vitest | Coverage: `packages/*` 85% lines or more, `services/*` 70% or more |
| Property | Hypothesis | Blackboard CAS, floor invariant (one speaker), rule engine operators, task state machine |
| Golden replay | pytest plus fixtures | Each game fixture produces identical events, world_state, and (FakeProvider) task traces |
| Contract | Schemathesis (OpenAPI), JSON Schema conformance | Every endpoint and every WS message type |
| Integration | pytest with real Postgres, Redis, and Chroma (CI service containers) | Session lifecycle with telemetry replay and FakeProvider |
| E2E | Playwright for Electron (Windows) | Section 8.2 M7 flow in replay mode |
| Perf | `tests/perf` (pytest-benchmark plus custom timers) | Bus throughput of 2,000 msgs/s or more. Event to first token with FakeProvider latency models. Regressions over 20% fail |
| LLM eval | `tests/eval` (offline, recorded contexts, rubric scored by a local judge model) | Nightly on a self-hosted GPU runner, if available. Report only, never blocking |
| HIL | `tests/hil/CHECKLIST.md` | Required sign-off per milestone for game, OBS, webcam, and GPU behaviour |

There are no network calls in tests (enforced with `pytest-socket`, except localhost service containers). FakeProvider scripts live in `packages/py/titan-testing`.

### 9.3 CI (GitHub Actions)
- `ci.yml` runs on every PR and on pushes to `main`:
  1. `lint`: ruff, mypy, eslint, tsc, import-linter, gitleaks (Ubuntu).
  2. `codegen-check` (Ubuntu).
  3. `test-py-linux`: unit, property, golden, contract, and integration tests with `postgres:16` and `redis:7` (with `requirepass`) containers plus Chroma started in the job, and the supervisor end-to-end test against the runner's PostgreSQL 16 binaries.
  4. `test-ts`: Vitest.
  5. `test-windows` (`windows-latest`): Windows-only tests (store scanners, registry fixtures, SCS shared-memory synthetic writer, supervisor job object, PresentMon parser), a portable Postgres smoke test, the supervisor end-to-end test (managed portable Postgres, Credential Manager, API `/system/status`, restart and orphan checks), Electron build, and Playwright e2e in replay mode with FakeProvider.
  6. `build-installer` on `main` only: an unsigned NSIS artifact.
- `release.yml` runs on `v*` tags: build the installer, attach SBOM (CycloneDX for Python and Node) and license report, and create a draft GitHub Release.
- Branch protection on `main`: all CI jobs required, 1 approving review, linear history, no force pushes. Dependabot (weekly) for pip, npm, and Actions.

### 9.4 Logging and observability
- **Logs:** structlog JSON lines, one file per process at `%LOCALAPPDATA%\Titan\logs\<process>\<process>.log`, rotating 50 MB x 10. Standard fields: `ts, level, process, pid, logger, event, session_id, correlation_id, agent_instance_id, task_id, trace_id`. Context vars set them automatically. Levels: `DEBUG` only behind a flag. `INFO` for lifecycle. `WARNING` for degraded states. `ERROR` with `exc_info`.
- **LLM observability:** every call goes to `llm_calls`. Prompt and response text is stored **only** with `logging.llm_prompts: true` (default false in release, true in dev), under `<session>/llm/` with a 30-day retention.
- **Metrics:** each service exposes internal counters and histograms (`prometheus_client` registry, aggregated by the API at `/system/metrics?format=prometheus` for power users). Key series: `bus_messages_total`, `llm_ttft_ms`, `llm_queue_depth`, `telemetry_frame_latency_ms`, `event_to_first_token_ms`, `ws_dropped_frames_total`, `resource_guard_level`.
- **Tracing:** OpenTelemetry SDK wired but the exporter is off by default (`otel.enabled: false`). It can be enabled to a local Jaeger for debugging. Trace context propagates in envelopes (`trace_id` field in `payload._trace`, internal only).
- **UI:** TOOLS > Logs (tail and filter by process and session) and Diagnostics bundle (`tools/diag-bundle.py`: logs, config with secrets removed, `/system/status`, versions).

### 9.5 Configuration
- Precedence (lowest to highest): `config/titan.yaml` in the app, then `%APPDATA%\Titan\config\titan.yaml`, then the `settings` table (UI-edited values), then environment variables `TITAN__<SECTION>__<KEY>` (for example `TITAN__API__PORT=8765`), then CLI flags. Loaded through `pydantic-settings` into one typed `TitanConfig`. Unknown keys fail at startup. The other files in `config/` (`models.yaml`, `safety.yaml`, `recording.yaml`, `egress.yaml`, `personas/`) are not part of `TitanConfig`: the subsystem that owns each one loads and validates it.
- Excerpt of `config/titan.yaml`:
```yaml
api:        { host: 127.0.0.1, port: 8765, cors_origins: ["app://titan"] }
postgres:   { host: 127.0.0.1, port: 54329, database: titan, user: titan, mode: managed, data_dir: "%LOCALAPPDATA%/Titan/data/pg" }
redis:      { url: "redis://127.0.0.1:63790/0" }        # password from keyring 'titan/redis'
chroma:     { host: 127.0.0.1, port: 8766, mode: managed, data_dir: "%LOCALAPPDATA%/Titan/data/chroma" }   # no auth in Chroma >= 1.0: loopback only
paths:      { recordings_root: "%USERPROFILE%/Videos/Titan" }
telemetry:  { publish_hz: 10, sample_hz: 1, chunk_minutes: 5 }
agents:     { tick_interval_ms: 10000, max_open_tasks_per_agent: 2, context_token_budget: 3000 }
director:   { tick_s: 15, report_interval_s: 300, can_spawn: false }
floor:      { min_gap_ms: 1500, max_words: 30, idle_invite_s: 45, arbitration_ms: 300 }
llm:        { max_tokens_per_minute: 12000, stale_drop_ms: 3000 }
recording:  { default_preset: "1080p60", min_free_gb: 20 }
safety:     { kill_hotkey: "Ctrl+Shift+F12" }        # actions disabled in P1 regardless
logging:    { level: INFO, llm_prompts: false }
network:    { offline_mode: false, allowlist_file: "config/egress.yaml" }
supervisor: { host: 127.0.0.1, port: 8769, processes: [postgres, redis, chroma, migrate, api], start_timeout_s: 20 }
metrics:    { sample_hz: 1, presentmon_path: null, nvml: true }
otel:       { enabled: false }
features:   { research: false, factory: false, actions: false, tts: false, video: false, publish: false }
```
Feature flags gate later-phase code paths. They stay `false` until the phase's exit criteria pass. Passwords never appear in YAML: `postgres.password` comes from Credential Manager in production and from `TITAN__POSTGRES__PASSWORD` in development and CI.

### 9.6 Security
- **Local-only surface.** Every listener binds `127.0.0.1`. The API requires the per-launch bearer token. Redis uses `requirepass` and Postgres uses a password and `pg_hba` limited to `host all all 127.0.0.1/32 scram-sha-256`. Chroma 1.x has no authentication, so it relies on its loopback bind (R16). These secrets are random and stored in Windows Credential Manager (`keyring`, service `titan`, entries `postgres` and `redis`): the supervisor generates the Postgres password at `initdb`, and the first-run wizard sets the Redis one when it configures Memurai. Development and CI pass them as `TITAN__POSTGRES__PASSWORD` and `TITAN__REDIS__PASSWORD` instead, and the dev Redis also runs with `requirepass`. The supervisor hands them to its children through the environment only, never argv.
- **Electron hardening:** `contextIsolation`, `sandbox`, no `nodeIntegration`, a strict CSP (`default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src http://127.0.0.1:8765 ws://127.0.0.1:8765 http://127.0.0.1:8767; img-src 'self' data: blob: http://127.0.0.1:8767; object-src 'none'; base-uri 'none'; form-action 'none'`; inline styles are required by MUI/Emotion, inline scripts never are), no remote content, `will-navigate` blocked, `setWindowOpenHandler` denies all, and Electron fuses set (`RunAsNode` off, `EnableNodeCliInspectArguments` off, `EnableNodeOptionsEnvironmentVariable` off, `GrantFileProtocolExtraPrivileges` off). The packaged renderer is served from a privileged `app://titan` scheme rather than `file://`, so it has a real origin: the API allows CORS only from `api.cors_origins` (default `app://titan`; the development shell adds its Vite dev-server origin), without credentials, because auth is the bearer header. Auto-update is off by default. When enabled, it only uses signed GitHub Releases.
- **YouTube OAuth (P7):** OAuth 2.0 for installed apps with **PKCE** and a loopback redirect (`http://127.0.0.1:<ephemeral>/oauth/callback`) opened in the system browser, never an embedded webview. Minimum scopes: `https://www.googleapis.com/auth/youtube.upload` and `https://www.googleapis.com/auth/youtube.readonly`, plus `https://www.googleapis.com/auth/yt-analytics.readonly` in P8. The refresh token lives in Credential Manager (`titan/youtube/<channel_id>`). Access tokens are memory-only. The client ID and secret come from the user's own Google Cloud project and are also stored in Credential Manager. Revocation is available from the UI. Every upload requires `upload_jobs.approved_at`, set only through the UI approval endpoint, which needs a typed confirmation.
- **Secrets hygiene:** gitleaks in CI and pre-commit. The logging processor redacts keys matching `(?i)(token|secret|password|authorization|api_key)`. The diagnostics bundle strips them too.
- **Plugins:** game and model-provider plugins are Python code with full privileges. Built-in plugins ship in the app. Third-party wheels load only from `%APPDATA%\Titan\plugins\` after the user explicitly trusts each one (SHA-256 recorded in `settings`). Integration installs (kRPC, SCS plugin) are hash-pinned.
- **Data ownership:** all data stays under user-controlled directories. "Export all data" (pg_dump plus files) and "Delete all data" are available in Settings. No telemetry is sent to Titan developers.

### 9.7 Network egress policy
- `network.offline_mode: true` blocks all outbound connections except `127.0.0.1`. This is enforced in the shared HTTP client factory (`titan_core.http`), which is the only allowed way to make HTTP calls (import-linter bans direct `httpx`/`requests` use outside it).
- The default allowlist (`config/egress.yaml`) contains only `registry.ollama.ai` (model pulls on user action) and `huggingface.co` (embedding model download at first run). Phase 2 adds research domains per source connector, each user-toggleable. Phase 7 adds `www.googleapis.com`, `oauth2.googleapis.com`, `accounts.google.com`, and `youtube.googleapis.com`.
- Only `titan-worker-io` (research and publish queues) and the model-pull job may use non-localhost egress. Every outbound request is logged (domain, path without query, status, bytes).

---

## 10. Appendices

### Appendix A: Phase 1 default teams and personas
Phase 1 teams are hand-authored in `games/<slug>/teams/default.yaml` and `config/personas/*.yaml`. All agents have `can_act: false`. `topics` feeds `role_relevance` in the Floor Manager.

**KSP: "Mission Control" team**
| Role | Persona | Personality | Subscriptions | Topics | Tick |
|---|---|---|---|---|---|
| director | **Flight Director "Wernher"** | Calm, decisive, dry wit | `ksp.*` severity warning or above, `task.*` | mission status, go/no-go | 15 s |
| flight_engineer | **"Gene"** | Precise, sardonic, worries about structure and heat | `ksp.staging`, `ksp.max_q`, `ksp.overheat_warning`, `ksp.high_g`, `ksp.stage_fuel_depleted` | engines, fuel, heat, structure | 10 s |
| mission_planner | **"Linus"** | Methodical, loves numbers, optimistic | `ksp.apoapsis_target`, `ksp.orbit_achieved`, `ksp.soi_changed` | trajectory, delta-v, burns | 10 s |
| navigator | **"Val"** (orbital mechanics) | Confident, teasing, quick | `ksp.launch`, `ksp.soi_changed`, `ksp.landed` | orbit, attitude, landing | 12 s |
| commentator.host | **"Jeb Radio"** | Showman, hypes moments, explains for viewers | all `ksp.*` with salience 0.6 or more | storytelling, recap, humour | 20 s |
Tools: `ksp.stage_dv`, `ksp.vis_viva_dv`, `ksp.twr`, `ksp.burn_time` (all read-only), plus the core tools.

**ETS2/ATS: "Haulage Crew" team** (shared template, currency and units from the manifest)
| Role | Persona | Personality | Subscriptions | Topics | Tick |
|---|---|---|---|---|---|
| director | **Dispatcher "Rosa"** | No-nonsense, protective of profit and reputation | `scs.job.*`, `vehicle.collision`, severity warning or above | job status, priorities | 15 s |
| driver_coach | **"Max"** | Laid-back veteran trucker, self-deprecating | `vehicle.speeding`, `vehicle.collision`, `scs.player.fined` | driving, road rules, traffic | 10 s |
| route_planner | **"Ingrid"** | Organised, map nerd | `scs.job.started`, `vehicle.fuel_low`, `scs.ferry`, `scs.train` | route, ETA, fuel stops | 12 s |
| economy_manager | **"Penny"** | Penny-pincher, deadpan | `scs.job.delivered`, `scs.player.fined`, `scs.player.refuel`, `vehicle.cargo_damage` | income, costs, fines | 12 s |
| maintenance | **"Wrench"** | Gruff, fatalistic about the truck | `vehicle.collision`, `vehicle.cargo_damage` | wear, damage, repairs | 20 s |
Tools: `scs.fuel_range`, `scs.eta`, `scs.job_profit` (read-only), plus the core tools.

**Persona system prompt template (shared skeleton):**
```
You are {{persona.display_name}}, the {{role_brief}} on an AI crew playing {{game.name}}.
Personality: {{persona.personality.traits|join(", ")}}. Speaking style: {{persona.speaking_style}}.
Rules: Speak in at most {{max_words}} words. Use only numbers present in WORLD_STATE or FACTS.
Never invent telemetry. Do not repeat earlier lines. Stay in character. Be entertaining but accurate.
You cannot control the game; you advise and comment.
WORLD_STATE: {{world_state}}   FACTS: {{facts}}   RISKS: {{risks}}   RECENT_CHAT: {{chat}}
MEMORIES (past episodes): {{memories}}   TRIGGER: {{trigger}}
```

### Appendix B: Glossary
- **Blackboard:** the per-session shared, versioned, sectioned key-value store through which agents coordinate (Section 6.4).
- **Envelope:** the standard bus message wrapper (Section 6.1).
- **Floor:** the single commentary speaking slot managed by the Floor Manager (Section 6.7).
- **Game adapter:** the plugin that integrates one game (Section 2.10).
- **HIL:** hardware-in-the-loop manual test on a real gaming PC.
- **Replay mode:** running a session from recorded telemetry with no game attached.
- **Resource Guard:** the degradation ladder that protects game FPS (Section 2.9.4).
- **Session clock:** the monotonic nanosecond clock (`perf_counter_ns`) that aligns every artifact.
- **Salience:** a 0 to 1 score of how interesting an event is, driving commentary urgency and highlight scoring.

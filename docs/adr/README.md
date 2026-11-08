# Architecture decision records

ADRs 0001 to 0019 record decisions D1 to D19 from the
[decision register](../titan-architecture-spec.md#0-decision-register). Those decisions are final for v1;
changing one needs a new ADR that supersedes the old one and a matching spec edit in the same PR.

New ADRs copy [`template.md`](template.md) and take the next free number.

| ADR                                                 | Decision | Topic                               | Status   |
| --------------------------------------------------- | -------- | ----------------------------------- | -------- |
| [0001](0001-postgres-over-sqlite.md)                | D1       | Structured database                 | Accepted |
| [0002](0002-chromadb-vector-store.md)               | D2       | Vector store                        | Accepted |
| [0003](0003-cpu-sentence-transformer-embeddings.md) | D3       | Embeddings                          | Accepted |
| [0004](0004-redis-streams-bus.md)                   | D4       | Message bus and realtime fan-out    | Accepted |
| [0005](0005-memurai-redis-on-windows.md)            | D5       | Redis on Windows                    | Accepted |
| [0006](0006-celery-background-jobs.md)              | D6       | Background jobs                     | Accepted |
| [0007](0007-langgraph-orchestration.md)             | D7       | Orchestration                       | Accepted |
| [0008](0008-ollama-behind-model-provider.md)        | D8       | LLM runtime                         | Accepted |
| [0009](0009-single-resident-model.md)               | D9       | Phase 1 model residency             | Accepted |
| [0010](0010-obs-websocket-recording.md)             | D10      | Recording                           | Accepted |
| [0011](0011-desktopcapturer-game-preview.md)        | D11      | In-app game view                    | Accepted |
| [0012](0012-krpc-ksp-telemetry.md)                  | D12      | KSP telemetry                       | Accepted |
| [0013](0013-scs-sdk-plugin-telemetry.md)            | D13      | ETS2/ATS telemetry                  | Accepted |
| [0014](0014-pydantic-schema-source-of-truth.md)     | D14      | Schema source of truth              | Accepted |
| [0015](0015-uv-pnpm-toolchains.md)                  | D15      | Python and Node toolchains          | Accepted |
| [0016](0016-electron-builder-packaging.md)          | D16      | Packaging                           | Accepted |
| [0017](0017-single-input-owner.md)                  | D17      | Game input (Phase 4)                | Accepted |
| [0018](0018-presentmon-fps.md)                      | D18      | Game FPS metric                     | Accepted |
| [0019](0019-uuidv7-and-session-clock.md)            | D19      | IDs and time                        | Accepted |
| [0020](0020-dev-docker-compose.md)                  | -        | Developer and CI service containers | Accepted |

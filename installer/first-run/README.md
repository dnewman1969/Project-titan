# First-run wizard steps

The desktop app shows a skeleton wizard on first launch (`apps/desktop/src/renderer/features/first-run`).
Full step automation (version checks, model pull, integration tests) lands in M10.T4.

| Step         | User action                     | Titan check (planned)                   |
| ------------ | ------------------------------- | --------------------------------------- |
| Ollama       | Install, pull `qwen3:8b`        | `GET /api/version` on `127.0.0.1:11434` |
| OBS          | OBS 30+, obs-websocket v5 :4455 | TCP/WebSocket probe via `titan-capture` |
| Memurai      | Redis 7 API with `requirepass`  | API dependency pill `redis`             |
| Models       | Pull pinned chat + embed models | `/models/pull` jobs                     |
| Integrations | kRPC / SCS plugin consent       | Game adapter inventory                  |

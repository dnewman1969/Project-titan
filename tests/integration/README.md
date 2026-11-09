# Integration tests

Cross-service tests against real Postgres, Redis and Chroma (CI service containers, or
`docker compose up -d` locally). Service tests skip unless `TITAN_REQUIRE_SERVICES=1` is set, in which
case a missing service fails the run. `test_supervisor_e2e.py` (M1 acceptance) starts the real
`titan-supervisor` with temporary data directories and runs when `TITAN_REQUIRE_SUPERVISOR_E2E=1`. From M5 onwards this folder adds session lifecycle tests
(API, orchestrator, telemetry replay and FakeProvider).

`test_learn_play_smoke.py` is the cloud-safe New session → learn → play happy path (FakeRedis + HIL);
it does **not** need `TITAN_REQUIRE_SERVICES`.

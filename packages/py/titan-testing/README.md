# titan-testing

Shared test fixtures for Project Titan.

- `titan_testing.db`: `pg_server` and `temp_db` pytest fixtures that create a throwaway database per test on the
  configured PostgreSQL server (skipped when unreachable unless `TITAN_REQUIRE_POSTGRES=1`).

The fake bus and FakeProvider scripts arrive with M3 and M6 (see `docs/titan-architecture-spec.md`, Section 8.2).

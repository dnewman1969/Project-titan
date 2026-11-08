# ADR 0001: Structured database (D1)

- **Status:** Accepted
- **Date:** 2026-11-08
- **Decision register:** D1 in [Section 0 of the architecture spec](../titan-architecture-spec.md#0-decision-register)

## Context

Structured database for Titan v1, a local-first Windows desktop application that must share one gaming PC with the
game, OBS and a local LLM.

## Decision

PostgreSQL 16, bundled portable binaries, Titan-managed

## Alternatives rejected

SQLite

## Rationale

Many processes write at once (API, orchestrator, telemetry host, Celery workers). Postgres gives row-level concurrency, JSONB with GIN indexes, `LISTEN/NOTIFY`, partial and generated-column indexes, and LangGraph's official Postgres checkpointer. SQLite's single writer would become the bottleneck at the first concurrent session.

## Consequences

- Titan ships and manages portable PostgreSQL 16 binaries (pinned in `third_party/manifest.yaml`); M1.T1 owns initdb, start and stop.
- The schema in Section 5.3 uses JSONB, partial indexes and `pg_trgm`; it is applied by Alembic (`packages/py/titan-db`).
- Every developer and CI job needs a reachable Postgres 16; see ADR 0020 for the dev setup.

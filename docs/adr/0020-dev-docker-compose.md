# ADR 0020: Developer and CI service containers

- **Status:** Accepted
- **Date:** 2026-11-08
- **Related:** ADR 0001 (D1), ADR 0002 (D2), ADR 0005 (D5)

## Context

Titan's runtime manages its own services: portable PostgreSQL 16 (D1), Memurai as Redis (D5) and a
Chroma server process (D2). The supervisor that starts them does not exist until M1. Developers and CI
still need Postgres 16, Redis 7 and Chroma from M0 onwards to run migrations and integration tests.
Section 9.3 already uses `postgres:16` and `redis:7` service containers in CI.

## Decision

A root `docker-compose.yml` starts `postgres:16.15`, `redis:7.4.12` and `chromadb/chroma:1.5.9` for
**development and CI only**. Host ports match `config/titan.yaml` (54329, 63790, 8766) and bind
`127.0.0.1`. Credentials are fixed, throwaway dev values (`titan`/`titan`).

The shipped application never uses Docker. D5's rejection of Docker/WSL2 Redis applies to end-user
installs and is unchanged.

## Alternatives rejected

- **Download the portable binaries for development as well.** That only works on Windows, while CI
  and many contributors run Linux. It is also M1.T1 work.
- **Ask every developer to install the services natively.** That leads to version drift and slower
  onboarding.

## Consequences

- `docker compose up -d && uv run titan-db upgrade` gives a working dev database. Docker Desktop is
  optional: native installs on the same ports work too (see `docs/dev-setup.md`).
- The dev containers run without Redis `requirepass` and without a Chroma token. Production secrets
  and auth arrive with M1.T1 and M1.T2. M1.T2 must confirm the token-auth mechanism of the pinned
  Chroma server version.
- CI's `test-py-linux` job uses the same image tags as service containers, so local and CI behaviour
  match.

# ADR 0005: Redis on Windows (D5)

- **Status:** Accepted
- **Date:** 2026-11-08
- **Decision register:** D5 in [Section 0 of the architecture spec](../titan-architecture-spec.md#0-decision-register)

## Context

Redis on Windows for Titan v1, a local-first Windows desktop application that must share one gaming PC with the
game, OBS and a local LLM.

## Decision

**Memurai** (native Windows, Redis 7 API) as a Windows service on `127.0.0.1:63790`

## Alternatives rejected

Docker/WSL2 Redis

## Rationale

No VM overhead on a gaming PC. Only `REDIS_URL` is used, so swapping to WSL2 Redis or Garnet is config-only. Its license is checked before distribution (risk R9).

## Consequences

- The first-run wizard installs Memurai; only `REDIS_URL` is consumed, so Redis, Garnet or WSL2 Redis also work.
- Memurai's licence must be reviewed before distribution (risk R9).

# ADR 0006: Background jobs (D6)

- **Status:** Accepted
- **Date:** 2026-11-08
- **Decision register:** D6 in [Section 0 of the architecture spec](../titan-architecture-spec.md#0-decision-register)

## Context

Background jobs for Titan v1, a local-first Windows desktop application that must share one gaming PC with the
game, OBS and a local LLM.

## Decision

Celery 5.4 with Redis broker. Windows pools: `threads` for I/O queues, `solo` for GPU and media queues

## Alternatives rejected

Dramatiq, arq

## Rationale

Celery is in the user's stack. Its prefork pool does not work on Windows, so Titan runs one process per queue class with an explicit pool (Section 2.7).

## Consequences

- Workers run one process per queue class with an explicit pool (Section 2.7), never prefork.
- Long GPU and media jobs use `solo`; I/O queues use `threads`.

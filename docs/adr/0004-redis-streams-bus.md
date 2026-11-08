# ADR 0004: Message bus and realtime fan-out (D4)

- **Status:** Accepted
- **Date:** 2026-11-08
- **Decision register:** D4 in [Section 0 of the architecture spec](../titan-architecture-spec.md#0-decision-register)

## Context

Message bus and realtime fan-out for Titan v1, a local-first Windows desktop application that must share one gaming PC with the
game, OBS and a local LLM.

## Decision

Redis Streams (plus pub/sub only for the kill switch)

## Alternatives rejected

ZeroMQ, NATS

## Rationale

Redis is already required by Celery. Streams give ordered, replayable, persistent logs with consumer groups, which the WebSocket gateway needs for resume-from-sequence.

## Consequences

- The WebSocket gateway resumes clients from a stream sequence.
- The kill switch uses pub/sub so it never waits behind a stream backlog.

# ADR 0007: Orchestration (D7)

- **Status:** Accepted
- **Date:** 2026-11-08
- **Decision register:** D7 in [Section 0 of the architecture spec](../titan-architecture-spec.md#0-decision-register)

## Context

Orchestration for Titan v1, a local-first Windows desktop application that must share one gaming PC with the
game, OBS and a local LLM.

## Decision

LangGraph `StateGraph`. One graph per agent role plus a Director graph, all hosted as asyncio tasks in **one orchestrator process per live session**, with Postgres checkpointing

## Alternatives rejected

One process per agent

## Rationale

Single GPU, single game: in-process routing is fast and simple. Redis Streams is the boundary to other processes, so scaling out later means adding consumer groups.

## Consequences

- All agent graphs for a session share one asyncio process; Redis Streams is the boundary to other processes.
- LangGraph checkpoints live in Postgres (the `lg` schema).

# ADR 0014: Schema source of truth (D14)

- **Status:** Accepted
- **Date:** 2026-11-08
- **Decision register:** D14 in [Section 0 of the architecture spec](../titan-architecture-spec.md#0-decision-register)

## Context

Schema source of truth for Titan v1, a local-first Windows desktop application that must share one gaming PC with the
game, OBS and a local LLM.

## Decision

Pydantic v2 models in `packages/py/titan-core/protocol`. JSON Schema and TypeScript types are **generated** from them

## Alternatives rejected

Hand-written TypeScript

## Rationale

One definition. CI fails if generated files drift.

## Consequences

- `tools/codegen.py` generates `schemas/*.json` and `packages/ts/protocol/src/generated/protocol.ts`; both are committed.
- The `codegen-check` CI job fails when generated files are stale, and a round-trip test validates shared samples in Python and zod.

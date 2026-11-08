# ADR 0009: Phase 1 model residency (D9)

- **Status:** Accepted
- **Date:** 2026-11-08
- **Decision register:** D9 in [Section 0 of the architecture spec](../titan-architecture-spec.md#0-decision-register)

## Context

Phase 1 model residency for Titan v1, a local-first Windows desktop application that must share one gaming PC with the
game, OBS and a local LLM.

## Decision

**One** resident chat model shared by all roles (`OLLAMA_MAX_LOADED_MODELS=1`)

## Alternatives rejected

One model per role

## Rationale

Swapping models costs 2 to 10 s and VRAM spikes cause game stutter. Per-role routing exists but defaults to the same tag until VRAM profile "24 GB+" is selected.

## Consequences

- `OLLAMA_MAX_LOADED_MODELS=1` by default; per-role routing defaults to the same tag.
- The "24 GB+" VRAM profile is the only one that enables per-role models.

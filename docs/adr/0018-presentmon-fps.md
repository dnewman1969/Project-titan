# ADR 0018: Game FPS metric (D18)

- **Status:** Accepted
- **Date:** 2026-11-08
- **Decision register:** D18 in [Section 0 of the architecture spec](../titan-architecture-spec.md#0-decision-register)

## Context

Game FPS metric for Titan v1, a local-first Windows desktop application that must share one gaming PC with the
game, OBS and a local LLM.

## Decision

PresentMon (Intel, MIT) console mode in the supervisor. GPU metrics via NVML; non-NVIDIA shows `n/a` in v1

## Alternatives rejected

Injecting an overlay

## Rationale

No injection into game processes, which keeps anti-cheat safe.

## Consequences

- PresentMon console runs under the supervisor and tracks the game PID (M1.T6).
- GPU metrics come from NVML; non-NVIDIA GPUs show `n/a` in v1.

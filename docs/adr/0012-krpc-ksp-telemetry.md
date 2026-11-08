# ADR 0012: KSP telemetry (D12)

- **Status:** Accepted
- **Date:** 2026-11-08
- **Decision register:** D12 in [Section 0 of the architecture spec](../titan-architecture-spec.md#0-decision-register)

## Context

KSP telemetry for Titan v1, a local-first Windows desktop application that must share one gaming PC with the
game, OBS and a local LLM.

## Decision

**kRPC** 0.5.x mod (protobuf over TCP 50000/50001)

## Alternatives rejected

Telemachus

## Rationale

kRPC has streams, a maintained Python client, and a **control API** that Phase 4 uses instead of keyboard injection, which is safer.

## Consequences

- Titan installs the pinned kRPC 0.5.x mod into KSP only after user consent, hash-verified (M4.T3).
- Phase 4 control uses the kRPC API rather than keyboard injection.

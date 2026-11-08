# ADR 0013: ETS2/ATS telemetry (D13)

- **Status:** Accepted
- **Date:** 2026-11-08
- **Decision register:** D13 in [Section 0 of the architecture spec](../titan-architecture-spec.md#0-decision-register)

## Context

ETS2/ATS telemetry for Titan v1, a local-first Windows desktop application that must share one gaming PC with the
game, OBS and a local LLM.

## Decision

SCS Telemetry SDK through the community **scs-sdk-plugin** (RenCloud, pinned version) exposing shared memory `Local\SCSTelemetry`, read by a versioned Python layout parser

## Alternatives rejected

Writing our own C++ plugin in Phase 1

## Rationale

Proven in both games with documented layout. Titan validates the plugin revision and refuses unknown layouts. Our own plugin is revisited in Phase 4 (ADR).

## Consequences

- Titan installs the pinned scs-sdk-plugin DLL after consent and refuses unknown shared-memory layouts.
- Writing our own SCS plugin is revisited at the start of Phase 4 in a new ADR.

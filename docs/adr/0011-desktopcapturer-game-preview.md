# ADR 0011: In-app game view (D11)

- **Status:** Accepted
- **Date:** 2026-11-08
- **Decision register:** D11 in [Section 0 of the architecture spec](../titan-architecture-spec.md#0-decision-register)

## Context

In-app game view for Titan v1, a local-first Windows desktop application that must share one gaming PC with the
game, OBS and a local LLM.

## Decision

Electron `desktopCapturer` preview of the game window (display only, never recorded)

## Alternatives rejected

Streaming OBS output into the app

## Rationale

Zero encode cost and no extra plugin.

## Consequences

- The in-app game view is a display-only `desktopCapturer` stream and is never recorded.

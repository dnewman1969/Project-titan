# ADR 0017: Game input (Phase 4) (D17)

- **Status:** Accepted
- **Date:** 2026-11-08
- **Decision register:** D17 in [Section 0 of the architecture spec](../titan-architecture-spec.md#0-decision-register)

## Context

Game input (Phase 4) for Titan v1, a local-first Windows desktop application that must share one gaming PC with the
game, OBS and a local LLM.

## Decision

One `titan-actions` process owns all input. API-level control first (kRPC). Virtual gamepad (ViGEmBus via `vgamepad`) for SCS games. `SendInput` keyboard and mouse last

## Alternatives rejected

PyAutoGUI everywhere

## Rationale

One choke point for the kill switch, rate limits, and foreground checks. PyAutoGUI is kept only for menu macros.

## Consequences

- Only `services/actions` may import `pyautogui`, `vgamepad`, `pydirectinput` or call `SendInput`; `tools/lint-imports` fails CI otherwise.
- `titan-actions` starts disarmed and is disabled in Phase 1 regardless of configuration.

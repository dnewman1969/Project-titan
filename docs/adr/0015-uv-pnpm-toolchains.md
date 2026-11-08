# ADR 0015: Python and Node toolchains (D15)

- **Status:** Accepted
- **Date:** 2026-11-08
- **Decision register:** D15 in [Section 0 of the architecture spec](../titan-architecture-spec.md#0-decision-register)

## Context

Python and Node toolchains for Titan v1, a local-first Windows desktop application that must share one gaming PC with the
game, OBS and a local LLM.

## Decision

Python 3.12 with `uv` workspaces; Node 22 LTS with `pnpm` workspaces; Electron 33+ with `electron-vite`

## Alternatives rejected

Poetry, npm

## Rationale

Fast, lockfile-exact, monorepo-native.

## Consequences

- `uv.lock` and `pnpm-lock.yaml` are committed and CI installs with `--frozen` / `--frozen-lockfile`.
- Electron 33 or newer with `electron-vite`; this repository pins a current major in `apps/desktop/package.json`.

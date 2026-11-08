# ADR 0016: Packaging (D16)

- **Status:** Accepted
- **Date:** 2026-11-08
- **Decision register:** D16 in [Section 0 of the architecture spec](../titan-architecture-spec.md#0-decision-register)

## Context

Packaging for Titan v1, a local-first Windows desktop application that must share one gaming PC with the
game, OBS and a local LLM.

## Decision

`electron-builder` NSIS installer. Ships embedded CPython 3.12 plus a frozen venv, portable PostgreSQL 16, and Chroma. Ollama, OBS, and Memurai are installed by a first-run wizard with links and version checks

## Alternatives rejected

PyInstaller

## Rationale

PyInstaller is fragile with torch, chromadb, and Celery. The venv approach is reproducible.

## Consequences

- The installer bundles embedded CPython with a frozen venv, portable PostgreSQL 16 and Chroma.
- Ollama, OBS and Memurai are installed by the first-run wizard, not bundled.

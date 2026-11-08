# ADR 0003: Embeddings (D3)

- **Status:** Accepted
- **Date:** 2026-11-08
- **Decision register:** D3 in [Section 0 of the architecture spec](../titan-architecture-spec.md#0-decision-register)

## Context

Embeddings for Titan v1, a local-first Windows desktop application that must share one gaming PC with the
game, OBS and a local LLM.

## Decision

`sentence-transformers` with `BAAI/bge-small-en-v1.5` (384-d) on **CPU**

## Alternatives rejected

GPU embeddings, Ollama embeddings

## Rationale

Keeps VRAM free for the game and the LLM. About 5 ms per chunk on a modern CPU is enough. The model name is stored in each collection's metadata, and changing it triggers a re-index.

## Consequences

- First run downloads `BAAI/bge-small-en-v1.5` from `huggingface.co` (allowlisted in `config/egress.yaml`).
- Changing the embedding model re-indexes the affected collections.

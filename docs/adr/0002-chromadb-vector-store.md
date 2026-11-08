# ADR 0002: Vector store (D2)

- **Status:** Accepted
- **Date:** 2026-11-08
- **Decision register:** D2 in [Section 0 of the architecture spec](../titan-architecture-spec.md#0-decision-register)

## Context

Vector store for Titan v1, a local-first Windows desktop application that must share one gaming PC with the
game, OBS and a local LLM.

## Decision

ChromaDB 0.6+/1.x in client-server mode on localhost

## Alternatives rejected

FAISS, pgvector

## Rationale

Chroma gives persistence, metadata filtering, and collection management out of the box. FAISS is only an index: no metadata filter, no persistence, no server. Server mode is required because Chroma's embedded `PersistentClient` is not safe across processes. Everything goes through the `VectorStore` interface, so pgvector stays a config-only swap later.

## Consequences

- A Chroma server process runs on `127.0.0.1:8766` with a token (M1.T2).
- Code talks to `VectorStore`, never to the Chroma client directly, so pgvector remains a config swap.

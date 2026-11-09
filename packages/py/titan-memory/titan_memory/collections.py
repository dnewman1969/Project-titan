"""Chroma collection definitions (Section 4.3)."""

from __future__ import annotations

from typing import Final

COLLECTION_NAMES: Final = ("knowledge", "memories", "strategies", "risks", "commentary")

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_EMBEDDING_DIM = 384
SCHEMA_VERSION = 1


def collection_metadata(
    *,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    embedding_dim: int = DEFAULT_EMBEDDING_DIM,
    schema_version: int = SCHEMA_VERSION,
) -> dict[str, str | int | float | bool]:
    return {
        "embedding_model": embedding_model,
        "embedding_dim": embedding_dim,
        "schema_version": schema_version,
        "hnsw:space": "cosine",
    }

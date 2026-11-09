"""Vector store protocol (Section 4.3)."""

from __future__ import annotations

from typing import Any, Protocol


class VectorStore(Protocol):
    tenant: str
    database: str

    async def ensure_collection(self, name: str, *, metadata: dict[str, Any] | None = None) -> None: ...

    async def upsert(
        self,
        collection: str,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
        embeddings: list[list[float]] | None = None,
    ) -> None: ...

    async def query(
        self,
        collection: str,
        *,
        query_embeddings: list[list[float]],
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    async def delete(self, collection: str, *, ids: list[str]) -> None: ...

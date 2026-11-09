"""Agent tool registry (M6.T3); `memory.search` wired to Chroma (M9 stub)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from titan_memory.chroma_store import ChromaVectorStore
from titan_models.embedder import Embedder, FakeEmbedder

ToolHandler = Callable[..., Awaitable[Any]]

_MEMORY_COLLECTION = "memories"


def _format_chroma_hits(body: dict[str, Any]) -> list[dict[str, Any]]:
    ids = body.get("ids")
    documents = body.get("documents")
    distances = body.get("distances")
    if not isinstance(ids, list) or not ids or not isinstance(ids[0], list):
        return []
    row_ids = ids[0]
    docs = documents[0] if isinstance(documents, list) and documents else []
    dists = distances[0] if isinstance(distances, list) and distances else []
    hits: list[dict[str, Any]] = []
    for index, mem_id in enumerate(row_ids):
        hit: dict[str, Any] = {"id": mem_id}
        if index < len(docs):
            hit["document"] = docs[index]
        if index < len(dists):
            hit["distance"] = dists[index]
        hits.append(hit)
    return hits


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolHandler] = {}

    def register(self, name: str, handler: ToolHandler) -> None:
        self._tools[name] = handler

    def names(self) -> list[str]:
        return sorted(self._tools)

    async def call(self, name: str, **kwargs: Any) -> Any:
        if name not in self._tools:
            msg = f"unknown tool {name!r}"
            raise KeyError(msg)
        return await self._tools[name](**kwargs)


def core_tools(
    *,
    chroma_url: str = "http://127.0.0.1:8766",
    embedder: Embedder | None = None,
) -> ToolRegistry:
    store = ChromaVectorStore(chroma_url)
    embed = embedder or FakeEmbedder()
    registry = ToolRegistry()

    async def bb_read(**_kwargs: Any) -> dict[str, Any]:
        return {"status": "stub"}

    async def bb_write(**_kwargs: Any) -> dict[str, Any]:
        return {"status": "stub"}

    async def memory_search(
        *,
        query: str,
        collection: str = _MEMORY_COLLECTION,
        n_results: int = 5,
        **_kwargs: Any,
    ) -> list[dict[str, Any]]:
        vectors = embed.embed([query])
        body = await store.query(collection, query_embeddings=vectors, n_results=n_results)
        return _format_chroma_hits(body)

    async def knowledge_search(**_kwargs: Any) -> list[dict[str, Any]]:
        return []

    registry.register("bb.read", bb_read)
    registry.register("bb.write", bb_write)
    registry.register("memory.search", memory_search)
    registry.register("knowledge.search", knowledge_search)
    return registry

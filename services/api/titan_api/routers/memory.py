"""Memory search API (M9 stub — Chroma loopback)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from titan_api.auth import Authenticated
from titan_core.config import load_config
from titan_core.health import check_chroma
from titan_memory.chroma_store import ChromaVectorStore
from titan_models.embedder import FakeEmbedder

router = APIRouter(tags=["memory"], dependencies=[Authenticated])


class MemorySearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    collection: str = "memories"
    n_results: int = Field(default=5, ge=1, le=50)


@router.get("/memory/status")
async def memory_status() -> dict[str, Any]:
    cfg = load_config()
    chroma = await check_chroma(cfg.chroma)
    return {
        "chroma": {
            "state": chroma.state,
            "version": chroma.version,
            "detail": chroma.detail,
        }
    }


@router.post("/memory/search")
async def memory_search(body: MemorySearchRequest) -> dict[str, Any]:
    cfg = load_config(user_config=False)
    store = ChromaVectorStore(cfg.chroma.url)
    embedder = FakeEmbedder()
    vectors = embedder.embed([body.query])
    try:
        raw = await store.query(body.collection, query_embeddings=vectors, n_results=body.n_results)
    except OSError as exc:
        return {"items": [], "degraded": True, "error": type(exc).__name__}
    items = _format_hits(raw)
    return {"items": items, "degraded": False}


def _format_hits(body: dict[str, Any]) -> list[dict[str, Any]]:
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

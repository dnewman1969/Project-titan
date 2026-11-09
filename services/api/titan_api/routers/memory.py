"""Memory API — search, browse, write, delete (M9 minimum)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from titan_api.auth import Authenticated
from titan_api.memory_ops import format_chroma_rows, format_query_hits, memory_store
from titan_core.config import load_config
from titan_core.health import check_chroma
from titan_core.ids import uuid7
from titan_memory.learnings import MEMORIES_COLLECTION
from titan_models.embedder import FakeEmbedder

router = APIRouter(tags=["memory"], dependencies=[Authenticated])


class MemorySearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    collection: str = MEMORIES_COLLECTION
    n_results: int = Field(default=8, ge=1, le=50)
    game_slug: str | None = None


class MemoryWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document: str = Field(min_length=1, max_length=8000)
    collection: str = MEMORIES_COLLECTION
    game_slug: str = "ksp"
    kind: str = "manual"
    session_id: str | None = None


class MemoryDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[str] = Field(min_length=1, max_length=100)
    collection: str = MEMORIES_COLLECTION


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


@router.get("/memory/browse")
async def memory_browse(
    collection: str = MEMORIES_COLLECTION,
    game_slug: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 40,
) -> dict[str, Any]:
    store = memory_store()
    where: dict[str, Any] | None = None
    if game_slug:
        where = {"game_slug": game_slug}
    try:
        raw = await store.get(collection, limit=limit, where=where)
    except OSError as exc:
        return {"items": [], "degraded": True, "error": type(exc).__name__}
    return {"items": format_chroma_rows(raw), "degraded": False}


@router.post("/memory/search")
async def memory_search(body: MemorySearchRequest) -> dict[str, Any]:
    store = memory_store()
    embedder = FakeEmbedder()
    vectors = embedder.embed([body.query])
    where: dict[str, Any] | None = None
    if body.game_slug:
        where = {"game_slug": body.game_slug}
    try:
        raw = await store.query(
            body.collection,
            query_embeddings=vectors,
            n_results=body.n_results,
            where=where,
        )
    except OSError as exc:
        return {"items": [], "degraded": True, "error": type(exc).__name__}
    return {"items": format_query_hits(raw), "degraded": False}


@router.post("/memory/items")
async def memory_write(body: MemoryWriteRequest) -> dict[str, Any]:
    store = memory_store()
    embedder = FakeEmbedder()
    mem_id = f"manual:{uuid7()}"
    meta: dict[str, Any] = {
        "game_slug": body.game_slug,
        "kind": body.kind,
        "section": "manual",
        "key": mem_id,
        "importance": 0.7,
        "confidence": 1.0,
    }
    if body.session_id:
        meta["session_id"] = body.session_id
    vectors = embedder.embed([body.document])
    try:
        await store.upsert(
            body.collection,
            ids=[mem_id],
            documents=[body.document],
            metadatas=[meta],
            embeddings=vectors,
        )
    except OSError as exc:
        return {"id": mem_id, "written": False, "degraded": True, "error": type(exc).__name__}
    return {"id": mem_id, "written": True, "degraded": False}


@router.post("/memory/delete")
async def memory_delete(body: MemoryDeleteRequest) -> dict[str, Any]:
    store = memory_store()
    try:
        await store.delete(body.collection, ids=body.ids)
    except OSError as exc:
        return {"deleted": 0, "degraded": True, "error": type(exc).__name__}
    return {"deleted": len(body.ids), "degraded": False}

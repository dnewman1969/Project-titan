"""Shared memory helpers for API routes and session lifecycle (M9)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from titan_core.config import load_config
from titan_core.http import HTTPError
from titan_core.logging import get_logger
from titan_db.repositories.blackboard import BlackboardRepository
from titan_memory.chroma_store import ChromaVectorStore
from titan_memory.learnings import LearningRow, fetch_prior_memory_lines, persist_session_learnings
from titan_models.embedder import FakeEmbedder

log = get_logger(__name__)


def memory_store() -> ChromaVectorStore:
    cfg = load_config(user_config=False)
    return ChromaVectorStore(cfg.chroma.url)


def format_chroma_rows(body: dict[str, Any]) -> list[dict[str, Any]]:
    ids = body.get("ids")
    if not isinstance(ids, list):
        return []
    documents_raw = body.get("documents")
    documents: list[Any] = documents_raw if isinstance(documents_raw, list) else []
    metadatas_raw = body.get("metadatas")
    metadatas: list[Any] = metadatas_raw if isinstance(metadatas_raw, list) else []
    distances = body.get("distances")
    dist_row = distances[0] if isinstance(distances, list) and distances else []
    items: list[dict[str, Any]] = []
    for index, mem_id in enumerate(ids):
        item: dict[str, Any] = {"id": mem_id}
        if index < len(documents) and isinstance(documents[index], str):
            item["document"] = documents[index]
        if index < len(metadatas) and isinstance(metadatas[index], dict):
            item["metadata"] = metadatas[index]
        if isinstance(dist_row, list) and index < len(dist_row):
            item["distance"] = dist_row[index]
        items.append(item)
    return items


def format_query_hits(body: dict[str, Any]) -> list[dict[str, Any]]:
    ids = body.get("ids")
    if not isinstance(ids, list) or not ids or not isinstance(ids[0], list):
        return []
    row_ids = ids[0]
    docs = body.get("documents")
    doc_row = docs[0] if isinstance(docs, list) and docs else []
    metas = body.get("metadatas")
    meta_row = metas[0] if isinstance(metas, list) and metas else []
    dists = body.get("distances")
    dist_row = dists[0] if isinstance(dists, list) and dists else []
    hits: list[dict[str, Any]] = []
    for index, mem_id in enumerate(row_ids):
        hit: dict[str, Any] = {"id": mem_id}
        if index < len(doc_row):
            hit["document"] = doc_row[index]
        if index < len(meta_row) and isinstance(meta_row[index], dict):
            hit["metadata"] = meta_row[index]
        if index < len(dist_row):
            hit["distance"] = dist_row[index]
        hits.append(hit)
    return hits


async def write_learning_on_session_end(
    db: AsyncSession,
    *,
    session_id: UUID,
    game_slug: str,
    session_title: str | None,
    outcome: str | None,
) -> dict[str, Any]:
    repo = BlackboardRepository(db)
    _bb_version, entries = await repo.snapshot(session_id, sections=["discoveries", "lessons", "notes"])
    rows = [
        LearningRow(
            section=entry.section,
            key=entry.key,
            value=entry.value if isinstance(entry.value, dict) else None,
            confidence=entry.confidence,
            created_at=entry.created_at,
        )
        for entry in entries
    ]
    store = memory_store()
    embedder = FakeEmbedder()
    result = await persist_session_learnings(
        store,
        embedder,
        session_id=session_id,
        game_slug=game_slug,
        session_title=session_title,
        outcome=outcome,
        rows=rows,
    )
    if result.get("written"):
        log.info("session_learnings_persisted", session_id=str(session_id), count=result["written"])
    elif result.get("degraded"):
        log.warning("session_learnings_degraded", session_id=str(session_id), error=result.get("error"))
    return result


async def seed_prior_memories_on_blackboard(
    db: AsyncSession,
    *,
    session_id: UUID,
    game_slug: str,
) -> int:
    repo = BlackboardRepository(db)
    if await repo.latest_entry(session_id, "notes", "prior.seed") is not None:
        return 0
    store = memory_store()
    embedder = FakeEmbedder()
    try:
        lines = await fetch_prior_memory_lines(
            store,
            embedder,
            game_slug=game_slug,
            query=f"{game_slug} session lessons discoveries play",
            n_results=5,
        )
    except (OSError, HTTPError, httpx.HTTPError) as exc:
        log.debug("prior_memory_seed_degraded", session_id=str(session_id), error=type(exc).__name__)
        return 0
    if not lines:
        return 0
    for index, line in enumerate(lines):
        bb_version = await repo.next_bb_version(session_id)
        await repo.append(
            session_id=session_id,
            section="notes",
            key=f"prior.{index:02d}",
            version=1,
            op="put",
            value={"text": line, "prior_memory": True},
            author="system:memory",
            confidence=0.8,
            evidence=[],
            bb_version=bb_version,
        )
    bb_version = await repo.next_bb_version(session_id)
    await repo.append(
        session_id=session_id,
        section="notes",
        key="prior.seed",
        version=1,
        op="put",
        value={"text": f"Loaded {len(lines)} prior memories for {game_slug}.", "prior_memory": True},
        author="system:memory",
        confidence=1.0,
        evidence=[],
        bb_version=bb_version,
    )
    return len(lines)

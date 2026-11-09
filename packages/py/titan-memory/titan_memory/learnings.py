"""Session learnings → Chroma `memories` (M9 minimum)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from titan_memory.chroma_store import ChromaVectorStore
from titan_models.embedder import Embedder

MEMORIES_COLLECTION = "memories"
LEARNING_SECTIONS = frozenset({"discoveries", "lessons"})


@dataclass(frozen=True)
class LearningRow:
    section: str
    key: str
    value: dict[str, Any] | None
    confidence: float | None
    created_at: datetime | None


def entry_text(value: dict[str, Any] | None) -> str | None:
    if not isinstance(value, dict):
        return None
    text = value.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return None


def should_persist_row(row: LearningRow) -> bool:
    if row.section in LEARNING_SECTIONS:
        return entry_text(row.value) is not None
    if row.section == "notes":
        if not isinstance(row.value, dict):
            return False
        if row.key.startswith("prior."):
            return entry_text(row.value) is not None
        if row.value.get("commentary") is True:
            return entry_text(row.value) is not None
    return False


def memory_kind(row: LearningRow) -> str:
    if row.section == "discoveries":
        return "discovery"
    if row.section == "lessons":
        value = row.value or {}
        if "ok" in value:
            return "lesson.feedback"
        if value.get("action_id"):
            return "lesson.proposal"
        return "lesson"
    return "prior" if row.key.startswith("prior.") else "commentary"


def memory_id(session_id: UUID, section: str, key: str) -> str:
    return f"session:{session_id}:{section}:{key}"


def build_rows(
    rows: list[LearningRow],
    *,
    session_id: UUID,
    game_slug: str,
    outcome: str | None,
    session_title: str | None,
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []
    for row in rows:
        if not should_persist_row(row):
            continue
        text = entry_text(row.value)
        if text is None:
            continue
        ids.append(memory_id(session_id, row.section, row.key))
        documents.append(text)
        occurred = row.created_at or datetime.now(tz=UTC)
        importance = 0.55 if row.section == "discoveries" else 0.75
        if row.section == "lessons" and isinstance(row.value, dict) and row.value.get("ok") is False:
            importance = 0.85
        metadatas.append(
            {
                "session_id": str(session_id),
                "game_slug": game_slug,
                "section": row.section,
                "key": row.key,
                "kind": memory_kind(row),
                "outcome": outcome or "unknown",
                "importance": importance,
                "confidence": float(row.confidence if row.confidence is not None else 0.7),
                "occurred_at": occurred.isoformat(),
                "session_title": session_title or "",
            }
        )
    if documents:
        summary = (
            f"Session {session_title or session_id} ({game_slug}) ended with outcome "
            f"{outcome or 'unknown'}; persisted {len(documents)} learnings."
        )
        ids.append(f"session:{session_id}:summary")
        documents.append(summary)
        metadatas.append(
            {
                "session_id": str(session_id),
                "game_slug": game_slug,
                "section": "summary",
                "key": "end",
                "kind": "session.summary",
                "outcome": outcome or "unknown",
                "importance": 0.6,
                "confidence": 1.0,
                "occurred_at": datetime.now(tz=UTC).isoformat(),
                "session_title": session_title or "",
            }
        )
    return ids, documents, metadatas


async def persist_session_learnings(
    store: ChromaVectorStore,
    embedder: Embedder,
    *,
    session_id: UUID,
    game_slug: str,
    session_title: str | None,
    outcome: str | None,
    rows: list[LearningRow],
) -> dict[str, Any]:
    ids, documents, metadatas = build_rows(
        rows,
        session_id=session_id,
        game_slug=game_slug,
        outcome=outcome,
        session_title=session_title,
    )
    if not ids:
        return {"written": 0, "degraded": False}
    vectors = embedder.embed(documents)
    try:
        await store.upsert(
            MEMORIES_COLLECTION,
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=vectors,
        )
    except OSError as exc:
        return {"written": 0, "degraded": True, "error": type(exc).__name__}
    return {"written": len(ids), "degraded": False}


async def fetch_prior_memory_lines(
    store: ChromaVectorStore,
    embedder: Embedder,
    *,
    game_slug: str,
    query: str,
    n_results: int = 5,
) -> list[str]:
    vectors = embedder.embed([query])
    try:
        raw = await store.query(MEMORIES_COLLECTION, query_embeddings=vectors, n_results=n_results)
    except Exception:
        return []
    docs = raw.get("documents")
    if not isinstance(docs, list) or not docs or not isinstance(docs[0], list):
        return []
    lines: list[str] = []
    for doc in docs[0]:
        if isinstance(doc, str) and doc.strip():
            lines.append(doc.strip())
    return lines

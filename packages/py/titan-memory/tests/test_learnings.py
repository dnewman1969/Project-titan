from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
import respx

from titan_memory.chroma_store import ChromaVectorStore
from titan_memory.learnings import (
    LearningRow,
    build_rows,
    entry_text,
    fetch_prior_memory_lines,
    memory_id,
    memory_kind,
    persist_session_learnings,
    should_persist_row,
)
from titan_models.embedder import FakeEmbedder


def test_should_persist_row_filters_sections() -> None:
    assert should_persist_row(
        LearningRow("discoveries", "a", {"text": "x"}, 0.8, None),
    )
    assert not should_persist_row(LearningRow("world_state", "a", {"text": "x"}, 0.8, None))
    assert should_persist_row(
        LearningRow("notes", "prior.01", {"text": "prior", "prior_memory": True}, 0.8, None),
    )
    assert should_persist_row(
        LearningRow("notes", "cmt", {"text": "hi", "commentary": True}, 0.5, None),
    )
    assert not should_persist_row(LearningRow("notes", "x", {"commentary": True}, 0.5, None))
    assert entry_text(None) is None
    assert entry_text({"text": "  "}) is None


def test_memory_kind_and_id() -> None:
    assert memory_kind(LearningRow("discoveries", "a", {"text": "x"}, 0.8, None)) == "discovery"
    assert memory_kind(LearningRow("lessons", "a", {"text": "x", "ok": True}, 0.8, None)) == "lesson.feedback"
    assert memory_kind(LearningRow("lessons", "a", {"text": "x", "action_id": "ksp"}, 0.8, None)) == "lesson.proposal"
    assert memory_kind(LearningRow("lessons", "a", {"text": "x"}, 0.8, None)) == "lesson"
    assert memory_kind(LearningRow("notes", "prior.0", {"text": "p"}, 0.8, None)) == "prior"
    assert memory_kind(LearningRow("notes", "n", {"text": "c"}, 0.8, None)) == "commentary"
    sid = UUID("00000000-0000-4000-8000-0000000000cc")
    assert memory_id(sid, "discoveries", "k") == f"session:{sid}:discoveries:k"


def test_build_rows_includes_summary() -> None:
    sid = UUID("00000000-0000-4000-8000-0000000000aa")
    rows = [
        LearningRow(
            section="discoveries",
            key="event.00001",
            value={"text": "Critical: ksp launch - note it for the playbook."},
            confidence=0.85,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        LearningRow(
            section="lessons",
            key="play.event.00001",
            value={"text": "Throttle to 80%", "action_id": "ksp.throttle"},
            confidence=0.9,
            created_at=None,
        ),
    ]
    ids, docs, metas = build_rows(
        rows, session_id=sid, game_slug="ksp", outcome="success", session_title="Test"
    )
    assert len(ids) == 3
    assert any(meta["kind"] == "discovery" for meta in metas)
    assert docs[-1].startswith("Session Test")
    failed = LearningRow(
        section="lessons",
        key="play.event.00002",
        value={"text": "Missed throttle", "ok": False},
        confidence=0.7,
        created_at=None,
    )
    _, _, meta_failed = build_rows([failed], session_id=sid, game_slug="ksp", outcome="failure", session_title="T")
    assert meta_failed[0]["importance"] == 0.85


@pytest.mark.asyncio
@respx.mock
async def test_persist_session_learnings_upserts_chroma() -> None:
    base = "http://127.0.0.1:8766"
    store = ChromaVectorStore(base)
    coll_id = "00000000-0000-4000-8000-000000000111"
    respx.get(f"{base}/api/v1/tenants/titan/databases/default/collections/memories").mock(
        return_value=httpx.Response(200, json={"id": coll_id, "name": "memories"})
    )
    upsert = respx.post(f"{base}/api/v1/tenants/titan/databases/default/collections/{coll_id}/upsert").mock(
        return_value=httpx.Response(200, json={})
    )
    sid = UUID("00000000-0000-4000-8000-0000000000bb")
    rows = [
        LearningRow(
            section="discoveries",
            key="a",
            value={"text": "Noted fuel low"},
            confidence=0.8,
            created_at=None,
        )
    ]
    result = await persist_session_learnings(
        store,
        FakeEmbedder(),
        session_id=sid,
        game_slug="ksp",
        session_title="Fuel test",
        outcome="partial",
        rows=rows,
    )
    assert result["written"] == 2
    assert upsert.called


@pytest.mark.asyncio
async def test_persist_session_learnings_empty_and_degraded() -> None:
    base = "http://127.0.0.1:8766"
    store = ChromaVectorStore(base)
    sid = UUID("00000000-0000-4000-8000-0000000000dd")
    empty = await persist_session_learnings(
        store,
        FakeEmbedder(),
        session_id=sid,
        game_slug="ksp",
        session_title=None,
        outcome=None,
        rows=[],
    )
    assert empty == {"written": 0, "degraded": False}

    async def boom(*_a: object, **_k: object) -> None:
        raise OSError("chroma down")

    store.upsert = boom  # type: ignore[method-assign]
    degraded = await persist_session_learnings(
        store,
        FakeEmbedder(),
        session_id=sid,
        game_slug="ksp",
        session_title="x",
        outcome="partial",
        rows=[
            LearningRow("discoveries", "a", {"text": "note"}, 0.8, None),
        ],
    )
    assert degraded["degraded"] is True
    assert degraded["written"] == 0


@pytest.mark.asyncio
@respx.mock
async def test_fetch_prior_memory_lines_success() -> None:
    base = "http://127.0.0.1:8766"
    store = ChromaVectorStore(base)
    coll_id = "00000000-0000-4000-8000-000000000222"
    respx.get(f"{base}/api/v1/tenants/titan/databases/default/collections/memories").mock(
        return_value=httpx.Response(200, json={"id": coll_id, "name": "memories"})
    )
    respx.post(f"{base}/api/v1/tenants/titan/databases/default/collections/{coll_id}/query").mock(
        return_value=httpx.Response(
            200,
            json={"documents": [["Line one", " ", "Line two"]]},
        )
    )
    lines = await fetch_prior_memory_lines(
        store,
        FakeEmbedder(),
        game_slug="ksp",
        query="ksp",
    )
    assert lines == ["Line one", "Line two"]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_prior_empty_when_chroma_errors() -> None:
    base = "http://127.0.0.1:8766"
    store = ChromaVectorStore(base)
    respx.get(f"{base}/api/v1/tenants/titan/databases/default/collections/memories").mock(
        return_value=httpx.Response(503, json={"error": "down"})
    )
    lines = await fetch_prior_memory_lines(
        store,
        FakeEmbedder(),
        game_slug="ksp",
        query="ksp lessons",
    )
    assert lines == []

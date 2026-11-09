from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
import respx

from titan_memory.chroma_store import ChromaVectorStore
from titan_memory.learnings import LearningRow, build_rows, persist_session_learnings
from titan_models.embedder import FakeEmbedder


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
    ids, docs, metas = build_rows(rows, session_id=sid, game_slug="ksp", outcome="success", session_title="Test")
    assert len(ids) == 3
    assert any(meta["kind"] == "discovery" for meta in metas)
    assert docs[-1].startswith("Session Test")


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

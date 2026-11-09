from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
import respx

from titan_memory.chroma_store import ChromaVectorStore
from titan_memory.learnings import (
    CONTRACT_FAILURE_KIND,
    FailedContract,
    LearningRow,
    build_rows,
    entry_text,
    exposed_failure_notes,
    failed_contract_from_lesson,
    failed_contract_memory_id,
    fetch_failed_contracts,
    fetch_prior_memory_lines,
    memory_id,
    memory_kind,
    persist_session_learnings,
    save_failed_contracts,
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
    assert (
        memory_kind(LearningRow("lessons", "a", {"text": "x", "action_id": "ksp"}, 0.8, None))
        == "lesson.proposal"
    )
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
    _, _, meta_failed = build_rows(
        [failed], session_id=sid, game_slug="ksp", outcome="failure", session_title="T"
    )
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


class FakeMemoryStore:
    """In-memory stand-in for the memories collection. No Chroma and no KSP."""

    def __init__(self) -> None:
        self.docs: dict[str, tuple[str, dict[str, object]]] = {}
        self.where: list[dict[str, object] | None] = []
        self.fail_get = False

    async def upsert(
        self,
        _collection: str,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, object]],
        embeddings: list[list[float]] | None = None,
    ) -> None:
        del embeddings
        for mem_id, document, metadata in zip(ids, documents, metadatas, strict=True):
            self.docs[mem_id] = (document, dict(metadata))

    async def query(
        self,
        _collection: str,
        *,
        query_embeddings: list[list[float]],
        n_results: int = 5,
        where: dict[str, object] | None = None,
    ) -> dict[str, object]:
        del query_embeddings, n_results, where
        return {"ids": [[]], "documents": [[]], "metadatas": [[]]}

    async def get(
        self,
        _collection: str,
        *,
        limit: int = 50,
        where: dict[str, object] | None = None,
        include: list[str] | None = None,
    ) -> dict[str, object]:
        del include
        self.where.append(where)
        if self.fail_get:
            raise OSError("store down")
        ids = list(self.docs)[:limit]
        return {
            "ids": ids,
            "documents": [self.docs[mem_id][0] for mem_id in ids],
            "metadatas": [self.docs[mem_id][1] for mem_id in ids],
        }


def _missed_lesson(key: str, title: str, reason: str) -> LearningRow:
    # Same lesson shape the career play loop writes on a miss.
    return LearningRow(
        section="lessons",
        key=f"career.fail.{key}",
        value={
            "text": f"Do not accept contract key `{key}` ({title}) again: {reason}.",
            "ok": False,
            "contract_key": key,
            "contract_title": title,
            "contract_type": "AltitudeRecord",
            "action_id": "ksp.contract.accept",
        },
        confidence=0.85,
        created_at=None,
    )


@pytest.mark.asyncio
async def test_failed_contract_survives_in_a_fake_store_for_the_same_game() -> None:
    store = FakeMemoryStore()
    embedder = FakeEmbedder()
    first = UUID("00000000-0000-4000-8000-0000000000a1")
    second = UUID("00000000-0000-4000-8000-0000000000a2")
    key = "altituderecord|reach 5000 m"
    title = "Reach 5,000 m"
    saved = await persist_session_learnings(
        store,
        embedder,
        session_id=first,
        game_slug="ksp",
        session_title="Career 1",
        outcome="failure",
        rows=[_missed_lesson(key, title, "out of fuel at 2200 m")],
    )
    assert saved["written"] == 3
    assert saved["degraded"] is False
    stable_id = failed_contract_memory_id("ksp", key)
    _document, meta = store.docs[stable_id]
    assert meta["kind"] == CONTRACT_FAILURE_KIND
    assert meta["contract_id"] == key
    assert meta["contract_title"] == title
    assert meta["failure_reason"] == "out of fuel at 2200 m"
    assert meta["session_id"] == str(first)
    assert meta["game_slug"] == "ksp"

    again = await save_failed_contracts(
        store,
        embedder,
        [
            FailedContract(
                contract_id=key,
                title=title,
                reason="accepting it did not move it to active",
                session_id=str(second),
                game_slug="ksp",
            )
        ],
    )
    assert again["written"] == 1
    other = await save_failed_contracts(
        store,
        embedder,
        [
            FailedContract(
                contract_id="survey|mun",
                title="Survey the Mun",
                reason="out of fuel",
                session_id=str(second),
                game_slug="ets2",
            )
        ],
    )
    assert other["written"] == 1

    found = await fetch_failed_contracts(store, game_slug="ksp")
    assert store.where[-1] == {"$and": [{"game_slug": "ksp"}, {"kind": CONTRACT_FAILURE_KIND}]}
    assert [(item.contract_id, item.reason, item.session_id) for item in found] == [
        (key, "accepting it did not move it to active", str(second))
    ]
    notes = exposed_failure_notes(found)
    assert notes[0][0] == "prior.fail.00"
    value = notes[0][1]
    assert value["ok"] is False
    assert value["contract_key"] == key
    assert "do not accept contract key" in str(value["text"]).lower()
    parsed = failed_contract_from_lesson(value, session_id="ignored", game_slug="ksp")
    assert parsed is not None
    assert parsed.contract_id == key
    assert await fetch_failed_contracts(store, game_slug="ets2") == [
        FailedContract(
            contract_id="survey|mun",
            title="Survey the Mun",
            reason="out of fuel",
            session_id=str(second),
            game_slug="ets2",
        )
    ]


@pytest.mark.asyncio
async def test_accept_lesson_is_not_a_failed_contract() -> None:
    store = FakeMemoryStore()
    sid = UUID("00000000-0000-4000-8000-0000000000a3")
    await persist_session_learnings(
        store,
        FakeEmbedder(),
        session_id=sid,
        game_slug="ksp",
        session_title="Career",
        outcome="success",
        rows=[
            LearningRow(
                section="lessons",
                key="career.accept.x",
                value={
                    "text": "Accepted Reach 5,000 m because the vessel can finish it.",
                    "ok": True,
                    "contract_key": "altituderecord|reach 5000 m",
                    "contract_title": "Reach 5,000 m",
                    "action_id": "ksp.contract.accept",
                },
                confidence=0.9,
                created_at=None,
            )
        ],
    )
    assert await fetch_failed_contracts(store, game_slug="ksp") == []
    assert all(not mem_id.startswith("failed-contract:") for mem_id in store.docs)


@pytest.mark.asyncio
async def test_fetch_failed_contracts_is_empty_when_the_store_errors() -> None:
    store = FakeMemoryStore()
    store.fail_get = True
    assert await fetch_failed_contracts(store, game_slug="ksp") == []
    store.upsert = _boom  # type: ignore[method-assign]
    saved = await save_failed_contracts(
        store,
        FakeEmbedder(),
        [
            FailedContract(
                contract_id="x",
                title="X",
                reason="broke",
                session_id="s",
                game_slug="ksp",
            )
        ],
    )
    assert saved["degraded"] is True
    assert saved["written"] == 0


async def _boom(*_args: object, **_kwargs: object) -> None:
    raise OSError("down")

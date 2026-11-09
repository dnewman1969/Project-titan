"""Session learnings → Chroma `memories` (M9 minimum)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from titan_models.embedder import Embedder

MEMORIES_COLLECTION = "memories"
LEARNING_SECTIONS = frozenset({"discoveries", "lessons"})
CONTRACT_FAILURE_KIND = "contract.failure"
_FAILURE_FETCH_LIMIT = 200


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


class LearningStore(Protocol):
    """The memories collection: Chroma in production, a fake in tests."""

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

    async def get(
        self,
        collection: str,
        *,
        limit: int = 50,
        where: dict[str, Any] | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class FailedContract:
    """A contract the crew missed. The next session for this game skips it."""

    contract_id: str
    title: str
    reason: str
    session_id: str
    game_slug: str


def failed_contract_memory_id(game_slug: str, contract_id: str) -> str:
    return f"failed-contract:{game_slug}:{contract_id}"


def failure_sentence(contract: FailedContract) -> str:
    """Same sentence the play loop already parses out of a lesson or prior note."""
    reason = contract.reason.strip().rstrip(".") or "it failed"
    title = contract.title.strip() or contract.contract_id
    return f"Do not accept contract key `{contract.contract_id}` ({title}) again: {reason}."


def failure_blackboard_value(contract: FailedContract) -> dict[str, Any]:
    """Note shape `failed_keys_from_rows` reads (`ok` false, `contract_key`, or the sentence)."""
    return {
        "text": failure_sentence(contract),
        "ok": False,
        "contract_key": contract.contract_id,
        "contract_id": contract.contract_id,
        "contract_title": contract.title,
        "failure_reason": contract.reason,
        "session_id": contract.session_id,
        "game_slug": contract.game_slug,
        "prior_memory": True,
    }


def exposed_failure_notes(contracts: Sequence[FailedContract]) -> list[tuple[str, dict[str, Any]]]:
    """Blackboard notes for one session, one per contract, stable order."""
    ordered = sorted(contracts, key=lambda item: item.contract_id)
    return [
        (f"prior.fail.{index:02d}", failure_blackboard_value(contract))
        for index, contract in enumerate(ordered)
    ]


def _plain(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split()).strip()


def _parts_from_sentence(text: str) -> tuple[str, str, str] | None:
    lowered = text.lower()
    marker = "contract key `"
    start = lowered.find(marker)
    if start < 0:
        return None
    rest = text[start + len(marker) :]
    end_key = rest.find("`")
    if end_key < 0:
        return None
    contract_id = rest[:end_key].strip()
    if not contract_id:
        return None
    after = rest[end_key + 1 :]
    again = ") again:"
    close = after.lower().rfind(again)
    if not after.startswith(" (") or close < 0:
        return contract_id, contract_id, "it failed"
    title = after[2:close].strip() or contract_id
    reason = after[close + len(again) :].strip().rstrip(".") or "it failed"
    return contract_id, title, reason


def failed_contract_from_lesson(
    value: dict[str, Any] | None,
    *,
    session_id: str,
    game_slug: str,
) -> FailedContract | None:
    """A missed-contract lesson, or None for an accept / ordinary lesson."""
    if not isinstance(value, dict):
        return None
    text = entry_text(value) or ""
    refused = value.get("ok") is False or "do not accept contract key" in text.lower()
    if not refused:
        return None
    parsed = _parts_from_sentence(text)
    contract_id = _plain(value.get("contract_id")) or _plain(value.get("contract_key"))
    title = _plain(value.get("contract_title"))
    reason = _plain(value.get("failure_reason"))
    if parsed is not None:
        contract_id = contract_id or parsed[0]
        title = title or parsed[1]
        reason = reason or parsed[2]
    if not contract_id:
        return None
    recorded_session = _plain(value.get("session_id")) or session_id
    recorded_game = _plain(value.get("game_slug")) or game_slug
    return FailedContract(
        contract_id=contract_id,
        title=title or contract_id,
        reason=reason or "it failed",
        session_id=recorded_session,
        game_slug=recorded_game,
    )


def _failure_metadata(contract: FailedContract, *, occurred_at: str) -> dict[str, Any]:
    return {
        "session_id": contract.session_id,
        "game_slug": contract.game_slug,
        "section": "lessons",
        "key": failed_contract_memory_id(contract.game_slug, contract.contract_id),
        "kind": CONTRACT_FAILURE_KIND,
        "contract_id": contract.contract_id,
        "contract_title": contract.title,
        "failure_reason": contract.reason,
        "outcome": "failure",
        "importance": 0.85,
        "confidence": 0.85,
        "occurred_at": occurred_at,
        "session_title": "",
    }


def failure_batch(
    contracts: Sequence[FailedContract],
    *,
    occurred_at: str | None = None,
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """One memories row per contract id. Later entries in `contracts` win."""
    stamp = occurred_at or datetime.now(tz=UTC).isoformat()
    chosen: dict[str, FailedContract] = {}
    for contract in contracts:
        if contract.contract_id and contract.game_slug:
            chosen[f"{contract.game_slug}:{contract.contract_id}"] = contract
    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []
    for contract in chosen.values():
        ids.append(failed_contract_memory_id(contract.game_slug, contract.contract_id))
        documents.append(failure_sentence(contract))
        metadatas.append(_failure_metadata(contract, occurred_at=stamp))
    return ids, documents, metadatas


def failures_from_rows(
    rows: Sequence[LearningRow],
    *,
    session_id: UUID,
    game_slug: str,
) -> list[FailedContract]:
    found: list[FailedContract] = []
    for row in rows:
        if row.section != "lessons":
            continue
        contract = failed_contract_from_lesson(
            row.value if isinstance(row.value, dict) else None,
            session_id=str(session_id),
            game_slug=game_slug,
        )
        if contract is not None:
            found.append(contract)
    return found


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
        metadata: dict[str, Any] = {
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
        if row.section == "lessons":
            missed = failed_contract_from_lesson(
                row.value if isinstance(row.value, dict) else None,
                session_id=str(session_id),
                game_slug=game_slug,
            )
            if missed is not None:
                metadata["contract_id"] = missed.contract_id
                metadata["contract_title"] = missed.title
                metadata["failure_reason"] = missed.reason
        metadatas.append(metadata)
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


async def save_failed_contracts(
    store: LearningStore,
    embedder: Embedder,
    contracts: Sequence[FailedContract],
) -> dict[str, Any]:
    """Upsert missed contracts so a later session for the same game can skip them."""
    ids, documents, metadatas = failure_batch(contracts)
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


async def persist_session_learnings(
    store: LearningStore,
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
    extra_ids, extra_docs, extra_meta = failure_batch(
        failures_from_rows(rows, session_id=session_id, game_slug=game_slug)
    )
    seen = set(ids)
    for mem_id, document, metadata in zip(extra_ids, extra_docs, extra_meta, strict=True):
        if mem_id in seen:
            continue
        seen.add(mem_id)
        ids.append(mem_id)
        documents.append(document)
        metadatas.append(metadata)
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


def _get_columns(raw: dict[str, Any]) -> tuple[list[Any], list[Any], list[Any]]:
    ids = raw.get("ids")
    metas = raw.get("metadatas")
    docs = raw.get("documents")
    id_row = ids if isinstance(ids, list) else []
    meta_row = metas if isinstance(metas, list) else []
    doc_row = docs if isinstance(docs, list) else []
    if id_row and isinstance(id_row[0], list):
        id_row = id_row[0]
        meta_row = meta_row[0] if meta_row and isinstance(meta_row[0], list) else []
        doc_row = doc_row[0] if doc_row and isinstance(doc_row[0], list) else []
    return id_row, doc_row, meta_row


def _contracts_from_get(raw: dict[str, Any], *, game_slug: str) -> list[FailedContract]:
    id_row, doc_row, meta_row = _get_columns(raw)
    best: dict[str, tuple[str, FailedContract]] = {}
    for index, _mem_id in enumerate(id_row):
        meta = meta_row[index] if index < len(meta_row) and isinstance(meta_row[index], dict) else None
        if not isinstance(meta, dict):
            continue
        if _plain(meta.get("game_slug")) != game_slug:
            continue
        kind = meta.get("kind")
        has_fields = bool(_plain(meta.get("contract_id")) and _plain(meta.get("failure_reason")))
        if kind != CONTRACT_FAILURE_KIND and not has_fields:
            continue
        document = doc_row[index] if index < len(doc_row) and isinstance(doc_row[index], str) else ""
        contract = failed_contract_from_lesson(
            {
                "text": document,
                "ok": False,
                "contract_id": meta.get("contract_id"),
                "contract_key": meta.get("contract_id"),
                "contract_title": meta.get("contract_title"),
                "failure_reason": meta.get("failure_reason"),
                "session_id": meta.get("session_id"),
                "game_slug": meta.get("game_slug"),
            },
            session_id=_plain(meta.get("session_id")),
            game_slug=game_slug,
        )
        if contract is None or contract.game_slug != game_slug:
            continue
        occurred = _plain(meta.get("occurred_at"))
        previous = best.get(contract.contract_id)
        if previous is None or occurred >= previous[0]:
            best[contract.contract_id] = (occurred, contract)
    return [item[1] for item in sorted(best.values(), key=lambda pair: pair[1].contract_id)]


async def fetch_failed_contracts(
    store: LearningStore,
    *,
    game_slug: str,
    limit: int = _FAILURE_FETCH_LIMIT,
) -> list[FailedContract]:
    """Missed contracts for this game, newest reason kept when the same id failed twice."""
    where: dict[str, Any] = {"$and": [{"game_slug": game_slug}, {"kind": CONTRACT_FAILURE_KIND}]}
    try:
        raw = await store.get(MEMORIES_COLLECTION, limit=limit, where=where)
    except Exception:
        return []
    return _contracts_from_get(raw, game_slug=game_slug)


async def fetch_prior_memory_lines(
    store: LearningStore,
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

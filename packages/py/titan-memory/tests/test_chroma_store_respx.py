from __future__ import annotations

import httpx
import pytest
import respx

from titan_memory.chroma_store import ChromaVectorStore


@pytest.mark.asyncio
@respx.mock
async def test_chroma_collection_lookup_and_upsert() -> None:
    base = "http://127.0.0.1:8766"
    store = ChromaVectorStore(base)
    coll_id = "00000000-0000-4000-8000-000000000001"
    respx.get(f"{base}/api/v1/tenants/titan/databases/default/collections/knowledge").mock(
        return_value=httpx.Response(200, json={"id": coll_id, "name": "knowledge"})
    )
    upsert = respx.post(f"{base}/api/v1/tenants/titan/databases/default/collections/{coll_id}/upsert").mock(
        return_value=httpx.Response(200, json={})
    )
    await store.upsert(
        "knowledge",
        ids=["1"],
        documents=["doc"],
        metadatas=[{"memory_id": "1"}],
        embeddings=[[0.1, 0.2, 0.3]],
    )
    assert upsert.called


@pytest.mark.asyncio
@respx.mock
async def test_chroma_ensure_collection_handles_conflict() -> None:
    base = "http://127.0.0.1:8766"
    store = ChromaVectorStore(base)
    route = respx.post(f"{base}/api/v1/tenants/titan/databases/default/collections").mock(
        return_value=httpx.Response(409, json={"error": "exists"})
    )
    await store.ensure_collection("memories")
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_chroma_query_and_delete() -> None:
    base = "http://127.0.0.1:8766"
    store = ChromaVectorStore(base)
    coll_id = "00000000-0000-4000-8000-000000000002"
    respx.get(f"{base}/api/v1/tenants/titan/databases/default/collections/risks").mock(
        return_value=httpx.Response(200, json={"id": coll_id, "name": "risks"})
    )
    query = respx.post(f"{base}/api/v1/tenants/titan/databases/default/collections/{coll_id}/query").mock(
        return_value=httpx.Response(200, json={"ids": [["a"]], "distances": [[0.1]]})
    )
    delete = respx.post(f"{base}/api/v1/tenants/titan/databases/default/collections/{coll_id}/delete").mock(
        return_value=httpx.Response(200, json={})
    )
    body = await store.query("risks", query_embeddings=[[0.0, 0.1]], n_results=1)
    assert body["ids"] == [["a"]]
    assert query.called
    await store.delete("risks", ids=["a"])
    assert delete.called


@pytest.mark.asyncio
@respx.mock
async def test_chroma_get_lists_documents() -> None:
    base = "http://127.0.0.1:8766"
    store = ChromaVectorStore(base)
    coll_id = "00000000-0000-4000-8000-000000000003"
    respx.get(f"{base}/api/v1/tenants/titan/databases/default/collections/memories").mock(
        return_value=httpx.Response(200, json={"id": coll_id, "name": "memories"})
    )
    get_route = respx.post(f"{base}/api/v1/tenants/titan/databases/default/collections/{coll_id}/get").mock(
        return_value=httpx.Response(200, json={"ids": ["a"], "documents": ["doc"], "metadatas": [{}]})
    )
    body = await store.get("memories", limit=5)
    assert body["ids"] == ["a"]
    assert get_route.called

from __future__ import annotations

import httpx
import pytest
import respx

from titan_orchestrator.agents.tools import core_tools


@pytest.mark.asyncio
@respx.mock
async def test_memory_search_tool_uses_chroma_mock() -> None:
    base = "http://127.0.0.1:8766"
    coll_id = "00000000-0000-4000-8000-000000000099"
    respx.get(f"{base}/api/v1/tenants/titan/databases/default/collections/memories").mock(
        return_value=httpx.Response(200, json={"id": coll_id, "name": "memories"})
    )
    query = respx.post(f"{base}/api/v1/tenants/titan/databases/default/collections/{coll_id}/query").mock(
        return_value=httpx.Response(
            200,
            json={
                "ids": [["mem-1"]],
                "documents": [["prior ascent checklist"]],
                "distances": [[0.11]],
            },
        )
    )
    tools = core_tools(chroma_url=base)
    hits = await tools.call("memory.search", query="ascent checklist", n_results=3)
    assert hits == [{"id": "mem-1", "document": "prior ascent checklist", "distance": 0.11}]
    assert query.called

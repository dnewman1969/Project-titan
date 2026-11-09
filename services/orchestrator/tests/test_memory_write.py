from __future__ import annotations

import httpx
import pytest
import respx

from titan_orchestrator.agents.tools import core_tools


@pytest.mark.asyncio
@respx.mock
async def test_memory_write_tool_upserts() -> None:
    base = "http://127.0.0.1:8766"
    coll_id = "00000000-0000-4000-8000-0000000000ee"
    respx.get(f"{base}/api/v1/tenants/titan/databases/default/collections/memories").mock(
        return_value=httpx.Response(200, json={"id": coll_id, "name": "memories"})
    )
    upsert = respx.post(f"{base}/api/v1/tenants/titan/databases/default/collections/{coll_id}/upsert").mock(
        return_value=httpx.Response(200, json={})
    )
    tools = core_tools(chroma_url=base)
    out = await tools.call("memory.write", document="Brake before downhill", game_slug="ets2")
    assert out["written"] is True
    assert upsert.called

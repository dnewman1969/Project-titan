from __future__ import annotations

import pytest

from titan_models.fake import FakeProvider
from titan_orchestrator.agents.graph import compile_agent_runtime


@pytest.mark.asyncio
async def test_agent_graph_runs_with_fake_provider() -> None:
    provider = FakeProvider(script=["Throttle up slowly."])
    graph = compile_agent_runtime(provider)
    result = await graph.ainvoke({"context": "You are Gene, flight engineer."}, config={"configurable": {"thread_id": "t1"}})
    assert result.get("reply")

"""WorldStateUpdater."""

from __future__ import annotations

from uuid import UUID

import pytest

from titan_orchestrator.world_state import WorldStateUpdater


class _Bb:
    put_calls = 0
    snapshot_calls = 0

    async def put(self, **kwargs: object) -> dict[str, object]:
        self.put_calls += 1
        return {}

    async def snapshot(self, **kwargs: object) -> tuple[int, list[dict[str, object]]]:
        self.snapshot_calls += 1
        return (1, [])


@pytest.mark.asyncio
async def test_ingest_telemetry_coalesces_to_one_per_second() -> None:
    bb = _Bb()
    updater = WorldStateUpdater(UUID(int=1), redis=object(), blackboard=bb)  # type: ignore[arg-type]
    assert await updater.ingest_telemetry({"summary": {"scene": "flight"}})
    assert not await updater.ingest_telemetry({"summary": {"scene": "flight"}})
    assert bb.put_calls == 1

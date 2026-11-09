"""run_session_loops lifecycle."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from uuid import UUID

import pytest

from titan_orchestrator.session_loops import run_session_loops


@dataclass
class StoppedRuntime:
    session_id: UUID
    redis: object
    _stopped: asyncio.Event = field(default_factory=asyncio.Event)

    def sessions(self) -> object:
        raise AssertionError("not used when stopped")


@pytest.mark.asyncio
async def test_run_session_loops_exits_when_stopped() -> None:
    runtime = StoppedRuntime(session_id=UUID(int=0), redis=object())
    runtime._stopped.set()
    await asyncio.wait_for(run_session_loops(runtime), timeout=2.0)

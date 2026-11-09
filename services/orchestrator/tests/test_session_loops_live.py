"""Session loops with redis stream fixtures."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from titan_core.protocol.telemetry import TELEMETRY_SCHEMA
from titan_core.streams import DATA_FIELD, session_events_stream, session_telemetry_stream
from titan_orchestrator.session_loops import run_session_loops


class _Bb:
    def __init__(self) -> None:
        self.puts: list[dict[str, Any]] = []

    async def put(self, **kwargs: Any) -> dict[str, object]:
        self.puts.append(kwargs)
        return {}

    async def snapshot(self, **kwargs: object) -> tuple[int, list[dict[str, object]]]:
        _ = kwargs
        return (1, [])


class _Bus:
    def __init__(self) -> None:
        self.published: list[object] = []

    async def publish(self, envelope: object) -> None:
        self.published.append(envelope)


class _EventRouter:
    def route(self, event: object, session_id: UUID) -> None:
        _ = event, session_id


class FakeRedis:
    def __init__(self, session_id: UUID, *, telemetry_json: str, event_json: str) -> None:
        sid = str(session_id)
        self._tel = session_telemetry_stream(sid)
        self._ev = session_events_stream(sid)
        self._telemetry_json = telemetry_json
        self._event_json = event_json
        self._tel_sent = False
        self._ev_sent = False

    async def xread(
        self, streams: dict[str, str], count: int = 8, block: int = 2000
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        _ = count, block
        await asyncio.sleep(0)
        name = next(iter(streams))
        if name == self._tel and not self._tel_sent:
            self._tel_sent = True
            return [(name, [("1-0", {DATA_FIELD: self._telemetry_json})])]
        if name == self._ev and not self._ev_sent:
            self._ev_sent = True
            return [(name, [("2-0", {DATA_FIELD: self._event_json})])]
        return []


class _Db:
    async def commit(self) -> None:
        return


@dataclass
class LoopRuntime:
    session_id: UUID
    redis: FakeRedis
    bb: _Bb = field(default_factory=_Bb)
    bus: _Bus = field(default_factory=_Bus)
    event_router: _EventRouter = field(default_factory=_EventRouter)
    _stopped: asyncio.Event = field(default_factory=asyncio.Event)

    @asynccontextmanager
    async def sessions(self) -> Any:
        yield _Db()

    def blackboard_service(self, _db: object) -> _Bb:
        return self.bb


def _telemetry_json(session_id: UUID) -> str:
    return json.dumps(
        {
            "schema": TELEMETRY_SCHEMA,
            "session_id": str(session_id),
            "game": "ksp",
            "adapter_version": "1.0.0",
            "seq": 1,
            "t_mono_ns": 1,
            "t_session_ms": 0,
            "t_game_s": 0,
            "paused": False,
            "scene": "flight",
            "domain": "space",
            "vehicle": {
                "name": None,
                "kind": "rocket",
                "position": None,
                "geo": None,
                "attitude": None,
                "velocity": {"speed_mps": 10, "vertical_mps": None, "horizontal_mps": None},
                "accel_g": None,
                "controls": None,
                "engine": None,
                "damage": {"overall": None, "parts": {}},
                "situation": "flying",
                "stage": None,
                "orbit": None,
            },
            "resources": [],
            "environment": None,
            "job": None,
        }
    )


def _ksp_launch_event_json(session_id: UUID) -> str:
    return json.dumps(
        {
            "id": str(UUID(int=5)),
            "session_id": str(session_id),
            "seq": 1,
            "type": "ksp.launch",
            "category": "game",
            "severity": "info",
            "salience": 0.7,
            "source": "rule:test",
            "t_mono_ns": 1,
            "t_session_ms": 1,
            "occurred_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
            "frame_seq": 1,
            "payload": {},
        }
    )


@pytest.mark.asyncio
async def test_run_session_loops_ingests_telemetry_and_play_event() -> None:
    sid = UUID(int=42)
    runtime = LoopRuntime(
        session_id=sid,
        redis=FakeRedis(
            sid,
            telemetry_json=_telemetry_json(sid),
            event_json=_ksp_launch_event_json(sid),
        ),
    )
    task = asyncio.create_task(run_session_loops(runtime, play_enabled=True))

    async def stop_soon() -> None:
        for _ in range(50):
            if runtime.redis._tel_sent and runtime.redis._ev_sent:
                runtime._stopped.set()
                return
            await asyncio.sleep(0.02)
        runtime._stopped.set()

    await asyncio.wait_for(stop_soon(), timeout=2.0)
    await asyncio.wait_for(task, timeout=2.0)

    assert any(p.get("section") == "discoveries" for p in runtime.bb.puts)
    lesson_puts = [p for p in runtime.bb.puts if p.get("section") == "lessons"]
    assert lesson_puts
    assert runtime.bus.published

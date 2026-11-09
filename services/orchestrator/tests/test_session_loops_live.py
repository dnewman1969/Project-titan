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

    async def ensure_group(self, _group: str) -> None:
        return

    async def read_group(self, *_a: object, **_k: object) -> list[tuple[str, object]]:
        return []

    async def ack(self, *_a: object) -> int:
        return 0

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


class _LatestRedis:
    def __init__(self, session_id: UUID, payload: str) -> None:
        self._stream = session_telemetry_stream(str(session_id))
        self._payload = payload

    async def xread(self, streams: dict[str, str], count: int = 8, block: int = 2000) -> list[object]:
        _ = streams, count, block
        await asyncio.sleep(0.01)
        return []

    async def xrevrange(self, stream: str, count: int = 1) -> list[tuple[str, dict[str, str]]]:
        _ = count
        if stream != self._stream:
            return []
        return [("9-0", {DATA_FIELD: self._payload})]


def _fly_proposals(runtime: LoopRuntime) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for envelope in runtime.bus.published:
        payload = getattr(envelope, "payload", None)
        if isinstance(payload, dict) and payload.get("action_id") == "ksp.fly":
            found.append(payload)
    return found


async def _run_flight(runtime: LoopRuntime, *, until: Any) -> None:
    task = asyncio.create_task(
        run_session_loops(runtime, play_enabled=True, game_slug="ksp", flight_period_s=0.05)
    )

    async def stop_soon() -> None:
        for _ in range(80):
            if until():
                runtime._stopped.set()
                return
            await asyncio.sleep(0.02)
        runtime._stopped.set()

    await asyncio.wait_for(stop_soon(), timeout=3.0)
    await asyncio.wait_for(task, timeout=3.0)


@pytest.mark.asyncio
async def test_flight_loop_proposes_heading_hold() -> None:
    sid = UUID(int=77)
    payload = json.dumps(
        {
            "scene": "flight",
            "paused": False,
            "vehicle": {
                "name": "Explorer",
                "situation": "pre_launch",
                "geo": {"lat_deg": 0.0, "lon_deg": 0.0, "alt_m": 70.0},
                "velocity": {"vertical_mps": 0.0},
            },
        }
    )
    runtime = LoopRuntime(session_id=sid, redis=_LatestRedis(sid, payload))  # type: ignore[arg-type]
    await _run_flight(runtime, until=lambda: bool(_fly_proposals(runtime)))
    proposals = _fly_proposals(runtime)
    assert proposals
    params = proposals[0]["params"]
    assert params["throttle"] == 1.0
    assert params["pitch_deg"] == 90.0
    assert params["heading_deg"] == 90.0
    assert params.get("stage") is True
    assert any(str(p.get("key", "")).startswith("play.flight.") for p in runtime.bb.puts)
    note = next(p for p in runtime.bb.puts if p.get("key") == "flight.decision")
    assert "Staging once" in str(note["value"]["text"])
    assert note["value"]["action_id"] == "ksp.fly"


@pytest.mark.asyncio
async def test_flight_loop_reports_missing_vessel() -> None:
    sid = UUID(int=78)
    payload = json.dumps({"scene": "space_center", "paused": False, "vehicle": None})
    runtime = LoopRuntime(session_id=sid, redis=_LatestRedis(sid, payload))  # type: ignore[arg-type]
    await _run_flight(
        runtime,
        until=lambda: any(p.get("key") == "flight.decision" for p in runtime.bb.puts),
    )
    assert _fly_proposals(runtime) == []
    note = next(p for p in runtime.bb.puts if p.get("key") == "flight.decision")
    assert "not steering" in str(note["value"]["text"])
    assert note["value"]["action_id"] is None


def _action_ids(runtime: LoopRuntime) -> list[str]:
    found: list[str] = []
    for envelope in runtime.bus.published:
        payload = getattr(envelope, "payload", None)
        if isinstance(payload, dict) and isinstance(payload.get("action_id"), str):
            found.append(payload["action_id"])
    return found


@pytest.mark.asyncio
async def test_flight_loop_accepts_a_contract_and_records_why() -> None:
    sid = UUID(int=79)
    payload = json.dumps(
        {
            "scene": "flight",
            "paused": False,
            "environment": {"body": "Kerbin"},
            "vehicle": {
                "name": "Explorer",
                "situation": "pre_launch",
                "geo": {"lat_deg": 0.0, "lon_deg": 0.0, "alt_m": 70.0},
                "velocity": {"vertical_mps": 0.0},
            },
            "career": {
                "mode": "career",
                "available": True,
                "reason": None,
                "funds": 10000,
                "science": 0,
                "reputation": 0,
                "offered": [
                    {
                        "type": "AltitudeRecord",
                        "title": "Reach an altitude of 5,000m",
                        "state": "offered",
                        "funds_advance": 1000,
                        "funds_completion": 5000,
                        "science_completion": 1,
                        "reputation_completion": 1,
                        "parameters": [
                            {
                                "title": "Reach an altitude of 5,000m",
                                "notes": "",
                                "completed": False,
                                "failed": False,
                                "optional": False,
                            }
                        ],
                    }
                ],
                "active": [],
                "failed": [],
                "vessel_parts": ["LV-T30 Liquid Fuel Engine", "FL-T400 Fuel Tank"],
                "liquid_fuel": 400,
                "oxidizer": 480,
                "solid_fuel": 0,
            },
        }
    )
    runtime = LoopRuntime(session_id=sid, redis=_LatestRedis(sid, payload))  # type: ignore[arg-type]
    await _run_flight(
        runtime,
        until=lambda: "ksp.contract.accept" in _action_ids(runtime),
    )
    assert "ksp.contract.accept" in _action_ids(runtime)
    why = next(
        put
        for put in runtime.bb.puts
        if put.get("section") == "lessons" and str(put.get("key", "")).startswith("career.accept.")
    )
    assert "Accepted" in str(why["value"]["text"])
    assert "Reach an altitude of 5,000m" in str(why["value"]["text"])
    board = next(put for put in runtime.bb.puts if put.get("key") == "career.board")
    assert "Offered:" in str(board["value"]["text"])
    assert "Active:" in str(board["value"]["text"])

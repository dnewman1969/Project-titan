"""Cloud-side New session → learn → play smoke (mocked HIL adapters).

Mirrors the Windows HIL happy path without a real game:

1. New session with no install → fixture source + HIL attach ready
2. Salient event → discovery + play proposal (learn)
3. Actions worker (HIL) executes proposal → in-memory control state changes
4. Orchestrator feedback → lesson outcome + arrogant commentary (play loop closed)

Runs in CI with FakeRedis / in-process bus; no Postgres, Redis service, or Windows required.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from titan_actions.drivers.hil_driver import hil_state
from titan_actions.drivers.krpc_driver import KrpcDriver
from titan_actions.drivers.scs_driver import ScsDriver
from titan_actions.executor import PlayExecutor
from titan_actions.play_env import PlaySettings
from titan_core.play_attach import PlayAttach, probe_attach, resolve_session_source
from titan_core.protocol.envelope import Address, Envelope, make_envelope
from titan_core.protocol.payloads import ActionExecuted, ActionPropose
from titan_core.protocol.telemetry import TELEMETRY_SCHEMA
from titan_core.streams import DATA_FIELD, session_events_stream, session_telemetry_stream
from titan_orchestrator.play_policy import clear_play_memory
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


class _EventRouter:
    def route(self, event: object, session_id: UUID) -> None:
        _ = event, session_id


class FakeRedis:
    """One-shot telemetry + event delivery (same shape as session_loops_live)."""

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


class ClosingBus:
    """Publish action.propose → execute via HIL → queue action.executed for feedback."""

    def __init__(self, *, session_id: UUID, executor: PlayExecutor) -> None:
        self.session_id = session_id
        self.executor = executor
        self.published: list[Envelope] = []
        self._pending: list[tuple[str, Envelope]] = []
        self._seq = 0

    async def ensure_group(self, _group: str) -> None:
        return

    async def publish(self, envelope: Envelope) -> str:
        self.published.append(envelope)
        if envelope.type == "action.propose":
            payload = ActionPropose.model_validate(envelope.payload)
            ok, err, latency_ms = self.executor.execute(payload.action_id, dict(payload.params))
            executed = ActionExecuted(
                proposal_id=envelope.id,
                ok=ok,
                latency_ms=latency_ms,
                error=err,
            )
            self._seq += 1
            out = make_envelope(
                type="action.executed",
                session_id=self.session_id,
                sender=Address(kind="agent", id="actions"),
                recipients=["broadcast"],
                visibility="internal",
                priority=5,
                payload=executed,
                correlation_id=envelope.id,
                causation_id=envelope.id,
            )
            self._pending.append((f"{self._seq}-0", out))
            self.published.append(out)
        return f"pub-{len(self.published)}"

    async def read_group(self, _group: str, _consumer: str, block_ms: int = 0) -> list[tuple[str, Envelope]]:
        _ = block_ms
        if self._pending:
            return [self._pending.pop(0)]
        await asyncio.sleep(0.01)
        return []

    async def ack(self, _group: str, entry_id: str) -> int:
        _ = entry_id
        return 1


class _Db:
    async def commit(self) -> None:
        return


@dataclass
class SmokeRuntime:
    session_id: UUID
    redis: FakeRedis
    bus: ClosingBus
    bb: _Bb = field(default_factory=_Bb)
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


def _speeding_event_json(session_id: UUID) -> str:
    return json.dumps(
        {
            "id": str(UUID(int=6)),
            "session_id": str(session_id),
            "seq": 1,
            "type": "vehicle.speeding",
            "category": "game",
            "severity": "warning",
            "salience": 0.75,
            "source": "rule:vehicle.speeding",
            "t_mono_ns": 1,
            "t_session_ms": 1,
            "occurred_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
            "frame_seq": 1,
            "payload": {"speed_mps": 30},
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


def test_new_session_fixture_resolves_hil_attach() -> None:
    """File → New session without an install: fixture source + HIL ready."""
    source = resolve_session_source(session_source=None, demo_telemetry=True, has_install=False)
    assert source == "fixture"
    attach = probe_attach(game_slug="ksp", source=source)
    assert attach.backend == "hil"
    assert attach.ready is True
    assert attach.source == "fixture"


@pytest.mark.asyncio
async def test_learn_play_smoke_closed_loop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: event → propose → HIL execute → feedback lesson + commentary."""
    monkeypatch.setenv("TITAN_PLAY_BACKEND", "hil")
    monkeypatch.setenv("TITAN_GAME_SLUG", "ksp")
    sid = UUID(int=4601)
    clear_play_memory(str(sid))

    settings = PlaySettings.from_environ()
    executor = PlayExecutor(session_id=sid, data_dir=tmp_path, settings=settings)
    bus = ClosingBus(session_id=sid, executor=executor)
    runtime = SmokeRuntime(
        session_id=sid,
        redis=FakeRedis(
            sid,
            telemetry_json=_telemetry_json(sid),
            event_json=_ksp_launch_event_json(sid),
        ),
        bus=bus,
    )

    task = asyncio.create_task(run_session_loops(runtime, play_enabled=True))  # type: ignore[arg-type]

    async def stop_when_feedback() -> None:
        for _ in range(200):
            feedback = [
                p
                for p in runtime.bb.puts
                if p.get("section") == "lessons" and str(p.get("key", "")).startswith("feedback.")
            ]
            notes = [
                p
                for p in runtime.bb.puts
                if p.get("section") == "notes" and str(p.get("key", "")).startswith("commentary.")
            ]
            if feedback and notes:
                runtime._stopped.set()
                return
            await asyncio.sleep(0.02)
        runtime._stopped.set()

    await asyncio.wait_for(stop_when_feedback(), timeout=5.0)
    await asyncio.wait_for(task, timeout=5.0)

    # Learn: discovery from salient event
    assert any(p.get("section") == "discoveries" for p in runtime.bb.puts)

    # Learn→play: proposal lesson + bus propose
    propose_lessons = [
        p
        for p in runtime.bb.puts
        if p.get("section") == "lessons" and str(p.get("key", "")).startswith("play.")
    ]
    assert propose_lessons
    proposes = [e for e in bus.published if e.type == "action.propose"]
    assert proposes
    propose_payload = ActionPropose.model_validate(proposes[0].payload)
    assert propose_payload.action_id == "ksp.throttle"

    # Play: HIL mutated control state + attach artifact
    state = hil_state()
    assert state["ksp"]["throttle"] == 0.75
    attach_path = tmp_path / "play_attach.json"
    assert attach_path.is_file()
    attach_body = json.loads(attach_path.read_text(encoding="utf-8"))
    assert attach_body["backend"] == "hil"
    assert attach_body["ready"] is True

    # Closed loop: feedback lesson ok + commentary banter
    feedback = [
        p
        for p in runtime.bb.puts
        if p.get("section") == "lessons" and str(p.get("key", "")).startswith("feedback.")
    ]
    assert feedback
    fb_value = feedback[0]["value"]
    assert isinstance(fb_value, dict)
    assert fb_value.get("ok") is True
    assert fb_value.get("action_id") == "ksp.throttle"

    commentary = [
        p
        for p in runtime.bb.puts
        if p.get("section") == "notes" and str(p.get("key", "")).startswith("commentary.")
    ]
    assert commentary
    note = commentary[0]["value"]
    assert isinstance(note, dict)
    assert note.get("commentary") is True
    assert note.get("ok") is True
    assert note.get("kind") in {"incredible", "feast"}


class _KrpcControl:
    throttle: float = 0.0

    def activate_next_stage(self) -> None:
        return


class _KrpcVessel:
    control = _KrpcControl()


class _KrpcConn:
    space_center = type("SC", (), {"active_vessel": _KrpcVessel()})()


class FakePad:
    def __init__(self) -> None:
        self.right: list[float] = []
        self.updates = 0

    def right_trigger_float(self, *, value_float: float) -> None:
        self.right.append(value_float)

    def update(self) -> None:
        self.updates += 1


async def _await_play_feedback(runtime: SmokeRuntime) -> None:
    for _ in range(200):
        feedback = [
            p
            for p in runtime.bb.puts
            if p.get("section") == "lessons" and str(p.get("key", "")).startswith("feedback.")
        ]
        notes = [
            p
            for p in runtime.bb.puts
            if p.get("section") == "notes" and str(p.get("key", "")).startswith("commentary.")
        ]
        if feedback and notes:
            runtime._stopped.set()
            return
        await asyncio.sleep(0.02)
    runtime._stopped.set()


@pytest.mark.asyncio
async def test_learn_play_krpc_backend_closed_loop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Event → proposal → mocked kRPC driver applies throttle (not HIL-only attach)."""
    monkeypatch.setenv("TITAN_PLAY_BACKEND", "krpc")
    monkeypatch.setenv("TITAN_GAME_SLUG", "ksp")
    sid = UUID(int=4602)
    clear_play_memory(str(sid))
    settings = PlaySettings.from_environ()
    attach = PlayAttach(source="live", backend="krpc", ready=True, message="mock krpc")
    _KrpcVessel.control.throttle = 0.0
    driver = KrpcDriver(
        host="127.0.0.1",
        rpc_port=50000,
        stream_port=50001,
        connect_fn=lambda *_a, **_k: _KrpcConn(),
    )
    executor = PlayExecutor(
        session_id=sid,
        data_dir=tmp_path,
        settings=settings,
        driver=driver,
        attach=attach,
    )
    bus = ClosingBus(session_id=sid, executor=executor)
    runtime = SmokeRuntime(
        session_id=sid,
        redis=FakeRedis(
            sid,
            telemetry_json=_telemetry_json(sid),
            event_json=_ksp_launch_event_json(sid),
        ),
        bus=bus,
    )
    task = asyncio.create_task(run_session_loops(runtime, play_enabled=True))  # type: ignore[arg-type]
    await asyncio.wait_for(_await_play_feedback(runtime), timeout=5.0)
    await asyncio.wait_for(task, timeout=5.0)

    assert _KrpcVessel.control.throttle == 0.75
    attach_body = json.loads((tmp_path / "play_attach.json").read_text(encoding="utf-8"))
    assert attach_body["backend"] == "krpc"
    assert attach_body["source"] == "live"
    proposes = [e for e in bus.published if e.type == "action.propose"]
    assert proposes
    assert ActionPropose.model_validate(proposes[0].payload).action_id == "ksp.throttle"


@pytest.mark.asyncio
async def test_learn_play_scs_vigem_backend_closed_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ETS2 speeding event → eased throttle on mocked ViGEm pad."""
    monkeypatch.setenv("TITAN_PLAY_BACKEND", "scs")
    monkeypatch.setenv("TITAN_GAME_SLUG", "ets2")
    sid = UUID(int=4603)
    clear_play_memory(str(sid))
    settings = PlaySettings.from_environ()
    pad = FakePad()
    attach = PlayAttach(source="live", backend="scs", ready=True, message="mock vigem")
    driver = ScsDriver(pad_factory=lambda: pad)
    executor = PlayExecutor(
        session_id=sid,
        data_dir=tmp_path,
        settings=settings,
        driver=driver,
        attach=attach,
    )
    bus = ClosingBus(session_id=sid, executor=executor)
    runtime = SmokeRuntime(
        session_id=sid,
        redis=FakeRedis(
            sid,
            telemetry_json=_telemetry_json(sid),
            event_json=_speeding_event_json(sid),
        ),
        bus=bus,
    )
    task = asyncio.create_task(run_session_loops(runtime, play_enabled=True))  # type: ignore[arg-type]
    await asyncio.wait_for(_await_play_feedback(runtime), timeout=5.0)
    await asyncio.wait_for(task, timeout=5.0)

    assert pad.right == [0.2]
    attach_body = json.loads((tmp_path / "play_attach.json").read_text(encoding="utf-8"))
    assert attach_body["backend"] == "scs"
    proposes = [e for e in bus.published if e.type == "action.propose"]
    assert ActionPropose.model_validate(proposes[0].payload).action_id == "scs.throttle"

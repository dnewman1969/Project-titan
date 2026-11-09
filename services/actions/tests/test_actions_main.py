"""titan-actions CLI."""

from __future__ import annotations

import asyncio
from uuid import UUID

import pytest

from titan_actions import __main__ as actions_main
from titan_core.protocol.envelope import Address, make_envelope
from titan_core.protocol.payloads import ActionPropose


def test_parse_args_session_id() -> None:
    sid = UUID(int=7)
    args = actions_main.parse_args(["--session-id", str(sid)])
    assert args.session_id == sid


@pytest.mark.asyncio
async def test_run_executes_low_risk_proposal(monkeypatch: pytest.MonkeyPatch) -> None:
    sid = UUID(int=8)
    acked: list[str] = []

    class _Bus:
        def __init__(self) -> None:
            self.published: list[object] = []

        async def ensure_group(self, _name: str) -> None:
            return

        async def publish(self, envelope: object) -> str:
            self.published.append(envelope)
            return "2-0"

        async def read_group(
            self, _group: str, _consumer: str, block_ms: int = 0
        ) -> list[tuple[str, object]]:
            _ = block_ms
            if acked:
                raise asyncio.CancelledError
            payload = ActionPropose.model_validate(
                {
                    "action_id": "ksp.throttle",
                    "params": {"throttle": 0.4},
                    "rationale": "test",
                    "risk": "low",
                    "expected_effect": "throttle",
                }
            )
            env = make_envelope(
                type="action.propose",
                session_id=sid,
                sender=Address(kind="agent", id="director"),
                recipients=["role:actions"],
                visibility="internal",
                priority=5,
                payload=payload,
                correlation_id=UUID(int=9),
            )
            return [("1-0", env)]

        async def ack(self, _group: str, entry_id: str) -> None:
            acked.append(entry_id)

    class _Redis:
        async def aclose(self) -> None:
            return

    monkeypatch.setattr(actions_main, "load_config", lambda: type("Cfg", (), {"redis": object()})())
    monkeypatch.setattr(actions_main, "redis_client", lambda _cfg, **_kwargs: _Redis())
    bus = _Bus()
    monkeypatch.setattr(actions_main, "SessionBus", lambda _r, _s: bus)

    assert await actions_main._run(sid, "ksp") == 0
    assert acked == ["1-0"]
    assert bus.published


@pytest.mark.asyncio
async def test_run_survives_idle_redis_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """An idle XREADGROUP must not kill the worker (socket timeout < block)."""
    import redis.exceptions

    sid = UUID(int=11)
    acked: list[str] = []
    captured: dict[str, float] = {}

    class _Bus:
        def __init__(self) -> None:
            self.published: list[object] = []
            self.reads = 0

        async def ensure_group(self, _name: str) -> None:
            return

        async def publish(self, envelope: object) -> str:
            self.published.append(envelope)
            return "2-0"

        async def read_group(
            self, _group: str, _consumer: str, block_ms: int = 0
        ) -> list[tuple[str, object]]:
            _ = block_ms
            self.reads += 1
            if self.reads == 1:
                raise redis.exceptions.TimeoutError("Timeout reading from 127.0.0.1:63790")
            if acked:
                raise asyncio.CancelledError
            payload = ActionPropose.model_validate(
                {
                    "action_id": "ksp.throttle",
                    "params": {"throttle": 0.4},
                    "rationale": "after idle",
                    "risk": "low",
                    "expected_effect": "throttle",
                }
            )
            env = make_envelope(
                type="action.propose",
                session_id=sid,
                sender=Address(kind="agent", id="director"),
                recipients=["role:actions"],
                visibility="internal",
                priority=5,
                payload=payload,
                correlation_id=UUID(int=12),
            )
            return [("1-0", env)]

        async def ack(self, _group: str, entry_id: str) -> None:
            acked.append(entry_id)

    class _Redis:
        async def aclose(self) -> None:
            return

    def _client(_cfg: object, timeout_s: float = 2.0) -> _Redis:
        captured["timeout_s"] = timeout_s
        return _Redis()

    monkeypatch.setenv("TITAN_PLAY_BACKEND", "hil")
    monkeypatch.setattr(actions_main, "load_config", lambda: type("Cfg", (), {"redis": object()})())
    monkeypatch.setattr(actions_main, "redis_client", _client)
    bus = _Bus()
    monkeypatch.setattr(actions_main, "SessionBus", lambda _r, _s: bus)

    assert await actions_main._run(sid, "ksp") == 0
    assert bus.reads >= 2
    assert acked == ["1-0"]
    assert bus.published
    assert captured["timeout_s"] > 2.0

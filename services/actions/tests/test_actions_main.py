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
        async def ensure_group(self, _name: str) -> None:
            return

        async def read_group(self, _group: str, _consumer: str, block_ms: int = 0) -> list[tuple[str, object]]:
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
    monkeypatch.setattr(actions_main, "redis_client", lambda _cfg: _Redis())
    monkeypatch.setattr(actions_main, "SessionBus", lambda _r, _s: _Bus())

    assert await actions_main._run(sid) == 0
    assert acked == ["1-0"]

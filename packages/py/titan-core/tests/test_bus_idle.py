"""Idle Redis stream reads must not raise out of the consumer."""

from __future__ import annotations

from uuid import UUID

import redis.exceptions

from titan_core.bus import SessionBus


class _IdleRedis:
    def __init__(self, exc: BaseException) -> None:
        self._exc = exc
        self.calls = 0

    async def xreadgroup(self, *_args: object, **_kwargs: object) -> object:
        self.calls += 1
        if self.calls == 1:
            raise self._exc
        return None


async def test_read_group_timeout_returns_empty() -> None:
    client = _IdleRedis(TimeoutError("Timeout reading from 127.0.0.1:63790"))
    bus = SessionBus(client, UUID(int=1))  # type: ignore[arg-type]
    assert await bus.read_group("actions", "actions-1", block_ms=2000) == []
    assert await bus.read_group("actions", "actions-1", block_ms=2000) == []
    assert client.calls == 2


async def test_read_group_redis_timeout_error_returns_empty() -> None:
    client = _IdleRedis(redis.exceptions.TimeoutError("Timeout reading from 127.0.0.1:63790"))
    bus = SessionBus(client, UUID(int=2))  # type: ignore[arg-type]
    assert await bus.read_group("actions", "actions-1", block_ms=2000) == []

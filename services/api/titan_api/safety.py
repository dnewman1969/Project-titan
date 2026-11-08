"""Kill-switch state (Sections 2.4 "Safety", 5.2 "Safety" and 6.9).

`kill()` changes the in-memory state and returns at once, so `POST /safety/kill` answers in well
under 50 ms whatever Redis is doing. Persisting to `titan:safety:state` and publishing on
`titan:safety:kill` happen in the background. Phase 1 has no input path, so nothing acts on the
kill yet; the state, the hotkey and the UI banner are wired now.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Any

import redis.asyncio as aioredis
import redis.exceptions

from titan_core.clock import utc_now
from titan_core.logging import get_logger
from titan_core.protocol.ws import SafetyState
from titan_core.streams import SAFETY_KILL, SAFETY_STATE

log = get_logger(__name__)

POLICY_VERSION = 1
Listener = Callable[[SafetyState], None]


def initial_state() -> SafetyState:
    return SafetyState(
        killed=False,
        armed=False,
        control_owner="none",
        last_kill_at=None,
        last_kill_source=None,
        policy_version=POLICY_VERSION,
    )


def _to_hash(state: SafetyState) -> dict[str, str]:
    return {key: json.dumps(value) for key, value in state.model_dump(mode="json").items()}


def _from_hash(fields: dict[str, str]) -> SafetyState:
    return SafetyState.model_validate({key: json.loads(value) for key, value in fields.items()})


class SafetyController:
    def __init__(self, redis: aioredis.Redis | None) -> None:
        self._redis = redis
        self._state = initial_state()
        self._listeners: set[Listener] = set()
        self._pending: set[asyncio.Task[None]] = set()

    @property
    def state(self) -> SafetyState:
        return self._state

    async def load(self) -> None:
        """Restore a kill that happened before an API restart. Disarmed whatever was stored."""
        if self._redis is None:
            return
        try:
            fields = await self._redis.hgetall(SAFETY_STATE)
            stored = _from_hash({str(k): str(v) for k, v in fields.items()}) if fields else None
        except (redis.exceptions.RedisError, OSError, ValueError) as exc:
            log.warning("safety_state_load_failed", error=type(exc).__name__)
            return
        if stored is not None:
            self._state = stored.model_copy(update={"armed": False, "control_owner": "none"})

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    def kill(self, source: str) -> SafetyState:
        self._state = self._state.model_copy(
            update={
                "killed": True,
                "armed": False,
                "control_owner": "none",
                "last_kill_at": utc_now(),
                "last_kill_source": source,
            }
        )
        log.warning("safety_kill", source=source)
        self._changed(publish=True)
        return self._state

    def resume(self) -> SafetyState:
        self._state = self._state.model_copy(update={"killed": False, "armed": False})
        log.info("safety_resume")
        self._changed(publish=False)
        return self._state

    def _changed(self, *, publish: bool) -> None:
        for listener in list(self._listeners):
            listener(self._state)
        if self._redis is not None:
            task = asyncio.create_task(self._persist(self._state, publish=publish))
            self._pending.add(task)
            task.add_done_callback(self._pending.discard)

    async def _persist(self, state: SafetyState, *, publish: bool) -> None:
        assert self._redis is not None  # noqa: S101 (checked by the caller)
        try:
            mapping: dict[Any, Any] = dict(_to_hash(state))
            await self._redis.hset(SAFETY_STATE, mapping=mapping)
            if publish:
                await self._redis.publish(SAFETY_KILL, state.model_dump_json())
        except (redis.exceptions.RedisError, OSError) as exc:
            log.error("safety_state_persist_failed", error=type(exc).__name__)

    async def drain(self) -> None:
        if self._pending:
            await asyncio.gather(*self._pending, return_exceptions=True)

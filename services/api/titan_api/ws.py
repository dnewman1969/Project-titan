"""WebSocket gateway (Section 5.3).

M1 serves `system.metrics` and `system.safety`. M5 adds `session.{sid}.telemetry` and
`session.{sid}.events` when the session Redis streams exist.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import re
import secrets
import time
from collections import deque
from collections.abc import Callable
from typing import Any, cast

import redis.asyncio as aioredis
import redis.exceptions
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from titan_api.safety import SafetyController
from titan_core.clock import utc_now
from titan_core.logging import get_logger
from titan_core.protocol.common import ProtocolModel
from titan_core.protocol.events import GameEvent
from titan_core.protocol.telemetry import TelemetryFrameUI
from titan_core.protocol.ws import (
    AUTH_TIMEOUT_S,
    CLOSE_BACKPRESSURE,
    CLOSE_UNAUTHORIZED,
    SEND_BUFFER_FRAMES,
    AckError,
    AckFrame,
    AuthFrame,
    ClientFrame,
    MsgFrame,
    PingFrame,
    PongFrame,
    SafetyState,
    SubscribeFrame,
    SystemMetrics,
    UnsubscribeFrame,
)
from titan_core.streams import (
    SYS_METRICS,
    entry_data,
    latest_entry,
    session_events_stream,
    session_telemetry_stream,
)

log = get_logger(__name__)

router = APIRouter()

SYSTEM_METRICS = "system.metrics"
SYSTEM_SAFETY = "system.safety"
JOBS = "jobs"
SESSION_CHANNEL = re.compile(r"^session\.[^.]+\.(chat|agents|telemetry|events|recording)$")
# The client learns that auth succeeded from this ack: AuthFrame has no req_id of its own.
AUTH_ACK_ID = "auth"
XREAD_BLOCK_MS = 1000
# `XREAD` with decode_responses: [(stream, [(entry id, fields)])]
StreamReply = list[tuple[str, list[tuple[str, dict[str, str]]]]] | None


class SendBuffer:
    """Per-connection send queue with the Section 5.3 backpressure rules.

    Frames with a `coalesce` key (telemetry, metrics) are latest-wins: a newer frame replaces a
    queued one, and when the buffer is full they are dropped first. `put()` returns False when a
    frame that must not be dropped does not fit; the caller then closes with 4408.
    """

    def __init__(self, limit: int = SEND_BUFFER_FRAMES) -> None:
        self.limit = limit
        self._frames: deque[tuple[str | None, str]] = deque()
        self._ready = asyncio.Event()

    def __len__(self) -> int:
        return len(self._frames)

    def put(self, text: str, *, coalesce: str | None = None) -> bool:
        if coalesce is not None:
            for index, (key, _) in enumerate(self._frames):
                if key == coalesce:
                    self._frames[index] = (key, text)
                    return True
            if len(self._frames) >= self.limit:
                return True
        elif len(self._frames) >= self.limit and not self._drop_one_droppable():
            return False
        self._frames.append((coalesce, text))
        self._ready.set()
        return True

    def _drop_one_droppable(self) -> bool:
        for index, (key, _) in enumerate(self._frames):
            if key is not None:
                del self._frames[index]
                return True
        return False

    async def get(self) -> str:
        while not self._frames:
            self._ready.clear()
            await self._ready.wait()
        return self._frames.popleft()[1]

    def wake(self) -> None:
        """Unblock `get()` during shutdown (no frame queued)."""
        self._ready.set()


def _seq_now() -> str:
    """A stream-id-shaped seq for frames that do not come from a stream (`system.safety`)."""
    return f"{time.time_ns() // 1_000_000}-0"


def _session_id_from_channel(channel: str, suffix: str) -> str | None:
    prefix = "session."
    if not channel.startswith(prefix) or not channel.endswith(suffix):
        return None
    body = channel[len(prefix) : -len(suffix)]
    return body or None


def _req_id(raw: str) -> str:
    with contextlib.suppress(ValueError, AttributeError):
        value = json.loads(raw).get("req_id")
        if isinstance(value, str):
            return value
    return ""


class Connection:
    def __init__(self, websocket: WebSocket, redis: aioredis.Redis, safety: SafetyController) -> None:
        self.websocket = websocket
        self.redis = redis
        self.safety = safety
        self.buffer = SendBuffer()
        self.overflow = asyncio.Event()
        self._subscriptions: dict[str, Callable[[], object]] = {}

    def send(self, frame: ProtocolModel, *, coalesce: str | None = None) -> None:
        if not self.buffer.put(frame.model_dump_json(), coalesce=coalesce):
            self.overflow.set()

    def ack(self, req_id: str, error: tuple[str, str] | None = None) -> None:
        self.send(
            AckFrame(
                op="ack",
                req_id=req_id,
                ok=error is None,
                error=None if error is None else AckError(code=error[0], detail=error[1]),
            )
        )

    async def run(self) -> None:
        self.ack(AUTH_ACK_ID)
        tasks = {
            asyncio.create_task(self._read(), name="ws-read"),
            asyncio.create_task(self._write(), name="ws-write"),
            asyncio.create_task(self.overflow.wait(), name="ws-overflow"),
        }
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            if self.overflow.is_set():
                log.warning("ws_backpressure_close", queued=len(self.buffer))
                with contextlib.suppress(RuntimeError, WebSocketDisconnect):
                    await self.websocket.close(code=CLOSE_BACKPRESSURE)
            for task in done:
                exc = None if task.cancelled() else task.exception()
                if exc is not None and not isinstance(exc, WebSocketDisconnect | RuntimeError):
                    raise exc
        finally:
            for cancel in self._subscriptions.values():
                cancel()
            self._subscriptions.clear()
            for task in tasks:
                task.cancel()
            self.buffer.wake()
            _done, pending = await asyncio.wait(tasks, timeout=2.0)
            if pending:
                for task in pending:
                    task.cancel()
                await asyncio.wait(pending, timeout=1.0)
            for task in tasks:
                if task.cancelled():
                    continue
                with contextlib.suppress(WebSocketDisconnect, RuntimeError):
                    exc = task.exception()
                    if exc is not None:
                        log.warning("ws_task_failed", task=task.get_name(), error=type(exc).__name__)

    async def _write(self) -> None:
        while True:
            await self.websocket.send_text(await self.buffer.get())

    async def _read(self) -> None:
        while True:
            raw = await self.websocket.receive_text()
            try:
                frame = ClientFrame.model_validate_json(raw).root
            except ValidationError as exc:
                self.ack(_req_id(raw), ("VALIDATION_FAILED", exc.errors()[0]["msg"]))
                continue
            if isinstance(frame, PingFrame):
                self.send(PongFrame(op="pong", req_id=frame.req_id))
            elif isinstance(frame, SubscribeFrame):
                await self._subscribe(frame)
            elif isinstance(frame, UnsubscribeFrame):
                cancel = self._subscriptions.pop(frame.channel, None)
                if cancel is not None:
                    cancel()
                self.ack(frame.req_id)
            elif isinstance(frame, AuthFrame):
                self.ack(AUTH_ACK_ID)

    async def _subscribe(self, frame: SubscribeFrame) -> None:
        channel = frame.channel
        if channel in self._subscriptions:
            self.ack(frame.req_id)
        elif channel == SYSTEM_METRICS:
            self.ack(frame.req_id)
            task = asyncio.create_task(self._follow_metrics(frame.since_seq), name="ws-metrics")
            self._subscriptions[channel] = task.cancel
        elif channel == SYSTEM_SAFETY:
            self.ack(frame.req_id)
            self._send_safety(self.safety.state)
            self._subscriptions[channel] = self.safety.subscribe(self._send_safety)
        elif channel == JOBS:
            self.ack(frame.req_id)
            self._subscriptions[channel] = lambda: None
        elif channel.endswith(".telemetry"):
            sid = _session_id_from_channel(channel, ".telemetry")
            if sid is None or not await self._session_stream_ready(sid):
                self.ack(frame.req_id, ("NOT_FOUND", "unknown session"))
                return
            self.ack(frame.req_id)
            task = asyncio.create_task(
                self._follow_session(
                    channel,
                    session_telemetry_stream(sid),
                    frame.since_seq,
                    kind="telemetry",
                ),
                name="ws-telemetry",
            )
            self._subscriptions[channel] = task.cancel
        elif channel.endswith(".events"):
            sid = _session_id_from_channel(channel, ".events")
            if sid is None or not await self._session_stream_ready(sid):
                self.ack(frame.req_id, ("NOT_FOUND", "unknown session"))
                return
            self.ack(frame.req_id)
            task = asyncio.create_task(
                self._follow_session(channel, session_events_stream(sid), frame.since_seq, kind="events"),
                name="ws-events",
            )
            self._subscriptions[channel] = task.cancel
        elif SESSION_CHANNEL.match(channel):
            self.ack(frame.req_id, ("NOT_FOUND", "unknown session"))
        else:
            self.ack(frame.req_id, ("VALIDATION_FAILED", f"unknown channel {channel!r}"))

    def _send_safety(self, state: SafetyState) -> None:
        self.send(self._msg(SYSTEM_SAFETY, _seq_now(), "safety.state", state))

    @staticmethod
    def _msg(channel: str, seq: str, type_: str, model: SafetyState | SystemMetrics) -> MsgFrame:
        ts = model.ts if isinstance(model, SystemMetrics) else utc_now()
        data: dict[str, Any] = model.model_dump(mode="json")
        return MsgFrame(op="msg", channel=channel, seq=seq, ts=ts, type=type_, data=data)

    def _send_metrics(self, entry_id: str, raw: str) -> None:
        try:
            metrics = SystemMetrics.model_validate_json(raw)
        except ValidationError:
            log.warning("ws_metrics_entry_invalid", seq=entry_id)
            return
        self.send(self._msg(SYSTEM_METRICS, entry_id, "system.metrics", metrics), coalesce=SYSTEM_METRICS)

    async def _session_stream_ready(self, session_id: str) -> bool:
        telemetry = session_telemetry_stream(session_id)
        events = session_events_stream(session_id)
        try:
            exists = await self.redis.exists(telemetry, events)
            return bool(exists)
        except (redis.exceptions.RedisError, OSError):
            return False

    async def _follow_session(
        self,
        channel: str,
        stream: str,
        since_seq: str | None,
        *,
        kind: str,
    ) -> None:
        last: str | None = since_seq
        failing = False
        coalesce = channel if kind == "telemetry" else None
        while True:
            try:
                if last is None:
                    latest = await latest_entry(self.redis, stream)
                    if latest is not None:
                        self._send_session_entry(channel, latest[0], latest[1], kind=kind, coalesce=coalesce)
                    last = latest[0] if latest is not None else "$"
                reply = await self.redis.xread({stream: last}, block=XREAD_BLOCK_MS, count=10)
                response = cast(StreamReply, reply)
            except (redis.exceptions.RedisError, OSError) as exc:
                if not failing:
                    log.warning("ws_session_redis_unavailable", channel=channel, error=type(exc).__name__)
                    failing = True
                await asyncio.sleep(1)
                continue
            failing = False
            for _stream, entries in response or []:
                for entry_id, fields in entries:
                    with contextlib.suppress(ValueError, ValidationError):
                        self._send_session_entry(
                            channel,
                            str(entry_id),
                            entry_data(fields),
                            kind=kind,
                            coalesce=coalesce,
                        )
                    last = str(entry_id)

    def _send_session_entry(
        self,
        channel: str,
        entry_id: str,
        raw: str,
        *,
        kind: str,
        coalesce: str | None,
    ) -> None:
        if kind == "telemetry":
            frame = TelemetryFrameUI.model_validate_json(raw)
            self.send(
                MsgFrame(
                    op="msg",
                    channel=channel,
                    seq=entry_id,
                    ts=utc_now(),
                    type="telemetry.frame",
                    data=frame.model_dump(mode="json", by_alias=True),
                ),
                coalesce=coalesce,
            )
            return
        event = GameEvent.model_validate_json(raw)
        self.send(
            MsgFrame(
                op="msg",
                channel=channel,
                seq=entry_id,
                ts=event.occurred_at,
                type="game.event",
                data=event.model_dump(mode="json", by_alias=True),
            )
        )

    async def _follow_metrics(self, since_seq: str | None) -> None:
        """Latest sample first (metrics are latest-wins, so older ones are skipped), then live."""
        last: str | None = since_seq
        failing = False
        while True:
            try:
                if last is None:
                    latest = await latest_entry(self.redis, SYS_METRICS)
                    if latest is not None:
                        self._send_metrics(*latest)
                    last = latest[0] if latest is not None else "$"
                reply = await self.redis.xread({SYS_METRICS: last}, block=XREAD_BLOCK_MS, count=10)
                response = cast(StreamReply, reply)
            except (redis.exceptions.RedisError, OSError) as exc:
                if not failing:
                    log.warning("ws_metrics_redis_unavailable", error=type(exc).__name__)
                    failing = True
                await asyncio.sleep(1)
                continue
            failing = False
            for _stream, entries in response or []:
                for entry_id, fields in entries:
                    with contextlib.suppress(ValueError):
                        self._send_metrics(str(entry_id), entry_data(fields))
                    last = str(entry_id)


@router.websocket("/ws")
async def gateway(websocket: WebSocket) -> None:
    state = websocket.app.state
    origin = websocket.headers.get("origin")
    if origin is not None and origin not in state.config.api.cors_origins:
        log.warning("ws_origin_rejected", origin=origin)
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        raw = await asyncio.wait_for(websocket.receive_text(), AUTH_TIMEOUT_S)
        frame = ClientFrame.model_validate_json(raw).root
    except (TimeoutError, ValidationError):
        frame = None
    except WebSocketDisconnect:
        return
    expected: str = state.launch_token
    if not isinstance(frame, AuthFrame) or not secrets.compare_digest(
        frame.token.encode(), expected.encode()
    ):
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return
    log.info("ws_connected", client=frame.client)
    await Connection(websocket, state.redis, state.safety).run()
    log.info("ws_disconnected", client=frame.client)

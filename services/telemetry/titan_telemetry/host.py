"""Telemetry host: adapter frame loop, writer, publisher (Section 7.1)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import redis.asyncio as aioredis

from titan_core.config import TelemetryConfig, TitanConfig
from titan_core.logging import get_logger
from titan_core.protocol.events import GameEvent
from titan_core.protocol.telemetry import TelemetryFrame, TelemetryFrameUI
from titan_core.streams import DATA_FIELD, session_events_stream, session_telemetry_stream, xadd_model
from titan_sdk_games.adapter import GameAdapter, RawFrame
from titan_sdk_games.exceptions import GameNotConnected
from titan_sdk_games.profiles import GameProfile
from titan_telemetry.loader import rules_path
from titan_telemetry.rules import RuleEngine
from titan_telemetry.writer import FrameWriter

log = get_logger(__name__)

BACKOFF_S = (1.0, 2.0, 5.0)


@dataclass
class HostContext:
    session_id: UUID
    game: str
    adapter: GameAdapter
    rules: RuleEngine
    writer: FrameWriter | None
    redis: aioredis.Redis | None
    cfg: TelemetryConfig
    recordings_root: Path


class TelemetryHost:
    def __init__(self, ctx: HostContext) -> None:
        self.ctx = ctx
        self._frame_seq = 0
        self._event_engine = ctx.rules
        self._prev: TelemetryFrame | None = None
        self._last_publish = 0.0
        self._last_sample = 0.0
        self._backoff_index = 0

    @classmethod
    def from_config(
        cls,
        config: TitanConfig,
        *,
        session_id: UUID,
        adapter: GameAdapter,
        game: str,
        profile: GameProfile,
        redis: aioredis.Redis | None = None,
        recordings_root: Path | None = None,
    ) -> TelemetryHost:
        rules = RuleEngine.from_yaml(rules_path(type(adapter)), session_id=session_id, game=game)
        writer = None
        if recordings_root is not None:
            session_dir = recordings_root / str(session_id) / "telemetry"
            writer = FrameWriter(session_dir, str(session_id), chunk_minutes=config.telemetry.chunk_minutes)
        del profile
        ctx = HostContext(
            session_id=session_id,
            game=game,
            adapter=adapter,
            rules=rules,
            writer=writer,
            redis=redis,
            cfg=config.telemetry,
            recordings_root=recordings_root or Path(),
        )
        return cls(ctx)

    async def run_live(self) -> None:
        while True:
            try:
                async for raw in self._frames():
                    await self._handle_frame(raw)
                self._backoff_index = 0
            except GameNotConnected:
                delay = BACKOFF_S[min(self._backoff_index, len(BACKOFF_S) - 1)]
                self._backoff_index = min(self._backoff_index + 1, len(BACKOFF_S) - 1)
                log.warning("telemetry_disconnected", delay_s=delay)
                await asyncio.sleep(delay)

    async def run_replay(self, frames: AsyncIterator[RawFrame], *, speed: int = 1) -> None:
        prev_ms: int | None = None
        async for raw in frames:
            t_ms = int(raw.get("t_session_ms", 0))
            if prev_ms is not None and t_ms > prev_ms:
                await asyncio.sleep((t_ms - prev_ms) / 1000.0 / speed)
            prev_ms = t_ms
            await self._handle_frame(raw)

    async def _frames(self) -> AsyncIterator[RawFrame]:
        async for frame in self.ctx.adapter.frames():
            yield frame

    async def _handle_frame(self, raw: RawFrame) -> None:
        self._frame_seq += 1
        normalized = self.ctx.adapter.normalize(raw)
        normalized = normalized.model_copy(
            update={
                "session_id": self.ctx.session_id,
                "game": self.ctx.game,
                "adapter_version": type(self.ctx.adapter).load_manifest().adapter_version,
                "seq": self._frame_seq,
            }
        )
        if self.ctx.writer is not None:
            self.ctx.writer.write(dict(raw), normalized)
        now = datetime.now(tz=UTC).timestamp()
        if now - self._last_publish >= 1.0 / self.ctx.cfg.publish_hz:
            await self._publish_telemetry(normalized)
            self._last_publish = now
        if now - self._last_sample >= 1.0 / self.ctx.cfg.sample_hz:
            if self.ctx.writer is not None:
                self.ctx.writer.sample(normalized)
            self._last_sample = now
        events = self._event_engine.evaluate(
            normalized, t_session_ms=normalized.t_session_ms, paused=normalized.paused
        )
        for item in self.ctx.adapter.detect_events(self._prev, normalized, raw):
            if isinstance(item, GameEvent):
                events.append(item)
        for event in events:
            await self._publish_event(event)
        self._prev = normalized

    async def _publish_telemetry(self, frame: TelemetryFrame) -> None:
        if self.ctx.redis is None:
            return
        ui = TelemetryFrameUI.model_validate(frame.model_dump(mode="json", by_alias=True))
        stream = session_telemetry_stream(str(self.ctx.session_id))
        await xadd_model(self.ctx.redis, stream, ui, maxlen=600)

    async def _publish_event(self, event: GameEvent) -> None:
        if self.ctx.redis is None:
            return
        stream = session_events_stream(str(self.ctx.session_id))
        fields = {DATA_FIELD: event.model_dump_json(by_alias=True)}
        await self.ctx.redis.xadd(stream, fields)  # type: ignore[arg-type]

    def close(self) -> None:
        if self.ctx.writer is not None:
            self.ctx.writer.close()

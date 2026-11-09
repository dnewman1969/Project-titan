"""Normalize frames, run rules, and build events for replay and live hosts."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from titan_core.protocol.events import GameEvent
from titan_core.protocol.telemetry import TelemetryFrame
from titan_sdk_games.adapter import GameAdapter, RawFrame
from titan_telemetry.rules import RuleEngine


@dataclass
class PipelineResult:
    frames: int
    events: list[GameEvent]


def iter_fixture(path: Path) -> Iterator[RawFrame]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            text = line.strip()
            if not text:
                continue
            data = json.loads(text)
            if isinstance(data, dict):
                yield RawFrame(data)


def run_fixture(
    adapter: GameAdapter,
    rules_path: Path,
    fixture_path: Path,
    *,
    session_id: UUID,
    game: str,
    adapter_version: str,
) -> PipelineResult:
    engine = RuleEngine.from_yaml(rules_path, session_id=session_id, game=game)
    events: list[GameEvent] = []
    prev_norm: TelemetryFrame | None = None
    frame_seq = 0
    base = datetime(2020, 1, 1, tzinfo=UTC)
    for raw in iter_fixture(fixture_path):
        frame_seq += 1
        norm = adapter.normalize(raw)
        norm = norm.model_copy(
            update={
                "session_id": session_id,
                "game": game,
                "adapter_version": adapter_version,
                "seq": frame_seq,
                "t_session_ms": int(raw.get("t_session_ms", frame_seq * 50)),
            }
        )
        t_ms = norm.t_session_ms
        adapter_events = adapter.detect_events(prev_norm, norm, raw)
        rule_events = engine.evaluate(norm, t_session_ms=t_ms, paused=norm.paused)
        for event in [*rule_events, *adapter_events]:
            if isinstance(event, GameEvent):
                stamped = event.model_copy(
                    update={
                        "session_id": session_id,
                        "frame_seq": frame_seq,
                        "occurred_at": base + timedelta(milliseconds=t_ms),
                    }
                )
                events.append(stamped)
        prev_norm = norm
    return PipelineResult(frames=frame_seq, events=events)


def canonical_events_ndjson(events: list[GameEvent]) -> str:
    lines = [e.model_dump_json(by_alias=True) for e in events]
    return "\n".join(lines) + ("\n" if lines else "")

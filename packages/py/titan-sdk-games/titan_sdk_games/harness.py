"""Adapter test harness: feeds recorded fixture frames through normalize/detect_events."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from titan_sdk_games.adapter import GameAdapter, RawFrame


@dataclass
class HarnessResult:
    frames: int
    events: list[Any]


class AdapterHarness:
    def __init__(self, adapter: GameAdapter) -> None:
        self.adapter = adapter

    def run_ndjson(self, path: Path) -> HarnessResult:
        frames = 0
        events: list[Any] = []
        prev = None
        for raw in _iter_ndjson(path):
            frame = RawFrame(raw)
            norm = self.adapter.normalize(frame)
            events.extend(self.adapter.detect_events(prev, norm, frame))
            prev = norm
            frames += 1
        return HarnessResult(frames=frames, events=events)


def _iter_ndjson(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            if isinstance(data, dict):
                yield data

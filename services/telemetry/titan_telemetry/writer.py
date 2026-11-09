"""Session telemetry file writer: zstd NDJSON chunks (Section 7.1)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import zstandard

from titan_core.protocol.telemetry import TelemetryFrame


@dataclass
class FrameWriter:
    root: Path
    session_id: str
    chunk_minutes: int = 5
    _chunk_index: int = 1
    _chunk_open: datetime | None = None
    _compressor: zstandard.ZstdCompressor | None = None
    _handle: Any = None
    samples: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, raw: dict[str, Any], normalized: TelemetryFrame) -> None:
        self._rotate_if_needed()
        record = {"raw": raw, "normalized": normalized.model_dump(mode="json", by_alias=True)}
        line = json.dumps(record, separators=(",", ":"), sort_keys=True) + "\n"
        if self._handle is None:
            self._open_chunk()
        if self._handle is None or self._compressor is None:
            return
        compressed = self._compressor.compress(line.encode("utf-8"))
        self._handle.write(compressed)

    def sample(self, normalized: TelemetryFrame) -> None:
        self.samples.append(normalized.model_dump(mode="json", by_alias=True))

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
        self._handle = None
        self._compressor = None

    def _rotate_if_needed(self) -> None:
        if self._chunk_open is None:
            return
        age_min = (datetime.now(tz=UTC) - self._chunk_open).total_seconds() / 60.0
        if age_min >= self.chunk_minutes:
            self.close()
            self._chunk_index += 1
            self._chunk_open = None

    def _open_chunk(self) -> None:
        name = f"frames-{self._chunk_index:04d}.ndjson.zst"
        path = self.root / name
        self._compressor = zstandard.ZstdCompressor()
        self._handle = path.open("wb")
        self._chunk_open = datetime.now(tz=UTC)

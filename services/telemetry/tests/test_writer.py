from __future__ import annotations

from pathlib import Path
from uuid import UUID

from titan_core.protocol.telemetry import TELEMETRY_SCHEMA, TelemetryFrame
from titan_telemetry.writer import FrameWriter


def _frame() -> TelemetryFrame:
    return TelemetryFrame.model_validate(
        {
            "schema": TELEMETRY_SCHEMA,
            "session_id": UUID(int=0),
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
                "velocity": {"speed_mps": 1, "vertical_mps": None, "horizontal_mps": None},
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
            "economy": None,
            "game_specific": {},
        }
    )


def test_frame_writer_writes_chunk(tmp_path: Path) -> None:
    writer = FrameWriter(tmp_path, "sess", chunk_minutes=60)
    writer.write({"raw": True}, _frame())
    writer.sample(_frame())
    writer.close()
    files = list(tmp_path.glob("frames-*.ndjson.zst"))
    assert files and files[0].stat().st_size > 0
    assert writer.samples

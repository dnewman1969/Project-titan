"""Shared-memory reader for SCS telemetry (Section 7.6)."""

from __future__ import annotations

import mmap
import os
import struct
from pathlib import Path
from typing import Any

from titan_game_scs.layout import ScsLayout


class ScsSharedMemory:
    """Opens a named mapping on Windows; in tests uses a file-backed mmap on POSIX."""

    def __init__(
        self, layout: ScsLayout, *, tag: str = "Local\\SCSTelemetry", path: Path | None = None
    ) -> None:
        self.layout = layout
        self._mmap: mmap.mmap | None = None
        if path is not None:
            self._mmap = mmap.mmap(path.open("r+b").fileno(), layout.size)
            return
        if os.name == "nt":
            self._mmap = mmap.mmap(-1, layout.size, tagname=tag, access=mmap.ACCESS_READ)
        else:
            raise OSError("SCS shared memory is only available on Windows without a test file path")

    def close(self) -> None:
        if self._mmap is not None:
            self._mmap.close()
        self._mmap = None

    def snapshot(self) -> dict[str, Any]:
        if self._mmap is None:
            raise OSError("mapping closed")
        return self.layout.read(self._mmap[: self.layout.size])


def encode_test_blob(layout: ScsLayout, values: dict[str, Any]) -> bytes:
    """Build a synthetic shared-memory block for unit tests."""
    blob = bytearray(layout.size)
    for name, spec in {**layout.header, **layout.fields}.items():
        if name not in values:
            continue
        value = values[name]
        fmt = "<" + spec.fmt
        size = struct.calcsize(fmt)
        struct.pack_into(fmt, blob, spec.offset, value if spec.fmt != "?" else bool(value))
        _ = size
    return bytes(blob)

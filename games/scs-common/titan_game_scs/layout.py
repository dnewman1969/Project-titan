"""SCS shared-memory layout loader (Section 7.6)."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_TYPE_FMT: dict[str, str] = {
    "u8": "B",
    "bool": "?",
    "i32": "i",
    "u32": "I",
    "u64": "Q",
    "f32": "f",
    "f64": "d",
}


@dataclass(frozen=True)
class FieldSpec:
    name: str
    offset: int
    fmt: str
    unit: str | None = None


@dataclass(frozen=True)
class ScsLayout:
    revision: int
    size: int
    header: dict[str, FieldSpec]
    fields: dict[str, FieldSpec]

    @classmethod
    def from_yaml(cls, path: Path) -> ScsLayout:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("layout must be a mapping")
        return cls(
            revision=int(data["revision"]),
            size=int(data["size"]),
            header=_field_map(data.get("header") or {}),
            fields=_field_map(data.get("fields") or {}),
        )

    def read(self, blob: bytes) -> dict[str, Any]:
        if len(blob) < self.size:
            blob = blob.ljust(self.size, b"\x00")
        out: dict[str, Any] = {}
        for spec in {**self.header, **self.fields}.values():
            fmt = "<" + spec.fmt
            (value,) = struct.unpack_from(fmt, blob, spec.offset)
            out[spec.name] = value
        return out


def _field_map(raw: dict[str, Any]) -> dict[str, FieldSpec]:
    out: dict[str, FieldSpec] = {}
    for name, row in raw.items():
        if not isinstance(row, dict):
            continue
        typ = str(row["type"])
        fmt = _TYPE_FMT.get(typ)
        if fmt is None:
            raise ValueError(f"unsupported layout type {typ!r}")
        out[name] = FieldSpec(name=name, offset=int(row["offset"]), fmt=fmt, unit=row.get("unit"))
    return out


def layout_path(revision: int) -> Path:
    root = Path(__file__).resolve().parent / "layouts"
    return root / "rencloud-1.12.yaml"

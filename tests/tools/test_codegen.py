"""Codegen tests (M0.T4): committed generated files are current, and the emitter is strict."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


codegen = _load("titan_tools_codegen", ROOT / "tools" / "codegen.py")


def test_generated_files_are_current() -> None:
    stale = codegen.stale_files(codegen.generate())
    assert not stale, f"run `pnpm codegen`: stale {[p.relative_to(ROOT).as_posix() for p in stale]}"


def test_generation_is_deterministic() -> None:
    assert codegen.generate() == codegen.generate()


def test_envelope_schema_matches_spec_contract() -> None:
    doc = json.loads((ROOT / "schemas" / "envelope.json").read_text(encoding="utf-8"))
    assert doc["$id"] == "https://titan.local/schemas/envelope.json"
    assert doc["additionalProperties"] is False
    assert set(doc["required"]) == {
        "id",
        "schema",
        "type",
        "session_id",
        "ts",
        "t_mono_ns",
        "sender",
        "recipients",
        "visibility",
        "priority",
        "payload",
    }
    assert doc["properties"]["schema"]["const"] == "titan.msg/1"


def test_check_mode_detects_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    outputs = codegen.generate()
    target = next(iter(outputs))
    fake = tmp_path / target.name
    fake.write_text("stale\n", encoding="utf-8")
    assert codegen.stale_files({fake: outputs[target]}) == [fake]


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "string", "format": "email"},
        {"type": "tuple"},
        {"prefixItems": [{"type": "string"}]},
        {"$ref": "https://example.com/x.json"},
    ],
)
def test_emitter_rejects_unsupported_schemas(schema: dict[str, object]) -> None:
    with pytest.raises(codegen.UnsupportedSchema):
        codegen.zod_expr(schema)


def test_emitter_basic_shapes() -> None:
    assert codegen.zod_expr({"anyOf": [{"type": "integer", "minimum": 0}, {"type": "null"}]}) == (
        "z.number().int().gte(0).nullable()"
    )
    assert codegen.zod_expr({"enum": ["a", "b"], "type": "string"}) == 'z.enum(["a", "b"])'
    assert codegen.zod_expr({"type": "object", "additionalProperties": {"type": "number"}}) == (
        "z.record(z.string(), z.number())"
    )
    assert codegen.zod_expr({"type": "array", "items": {"$ref": "#/$defs/X"}, "minItems": 1}) == (
        "z.array(XSchema).min(1)"
    )

"""Round-trip test (M0.T4): samples validate identically with Pydantic and the generated JSON Schemas.

The TypeScript side runs the same samples through the generated zod schemas
(`packages/ts/protocol/tests/samples.test.ts`).
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ValidationError

from titan_core.protocol import MESSAGE_TYPES, envelope, events, payloads, telemetry, ws

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "tests" / "contract" / "samples"
SCHEMAS = ROOT / "schemas"


def _models() -> dict[str, type[BaseModel]]:
    found: dict[str, type[BaseModel]] = {}
    for module in (envelope, events, payloads, telemetry, ws):
        for name, obj in vars(module).items():
            if inspect.isclass(obj) and issubclass(obj, BaseModel) and obj.__module__ == module.__name__:
                found[name] = obj
    return found


MODELS = _models()


def _merged_defs() -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for path in sorted(SCHEMAS.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        defs = doc.pop("$defs", {})
        merged.update(defs)
        if "properties" in doc:
            body = {k: v for k, v in doc.items() if not k.startswith(("$", "x-titan"))}
            merged[doc["title"]] = body
    return merged


DEFS = _merged_defs()


def _validator(def_name: str) -> Draft202012Validator:
    schema = {"$ref": f"#/$defs/{def_name}", "$defs": DEFS}
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)


def _cases() -> Iterator[tuple[str, dict[str, Any]]]:
    for path in sorted(SAMPLES.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for i, case in enumerate(data.get("cases", [data])):
            yield f"{path.stem}[{i}]", case


def _expand(case: dict[str, Any]) -> Iterator[tuple[str, type[BaseModel], Any, bool]]:
    for expected, items in (("valid", case.get("valid", [])), ("invalid", case.get("invalid", []))):
        for item in items:
            if case.get("byType"):
                model = MESSAGE_TYPES[item["type"]]
                yield model.__name__, model, item["payload"], expected == "valid"
            else:
                yield case["def"], MODELS[case["def"]], item, expected == "valid"


ITEMS = [
    pytest.param(def_name, model, item, ok, id=f"{case_id}:{def_name}:{'ok' if ok else 'bad'}{n}")
    for case_id, case in _cases()
    for n, (def_name, model, item, ok) in enumerate(_expand(case))
]


def test_samples_exist() -> None:
    assert len(ITEMS) >= 40


@pytest.mark.parametrize(("def_name", "model", "item", "ok"), ITEMS)
def test_pydantic_and_json_schema_agree(def_name: str, model: type[BaseModel], item: Any, ok: bool) -> None:
    errors = list(_validator(def_name).iter_errors(item))
    try:
        parsed = model.model_validate(item)
        pydantic_ok = True
    except ValidationError:
        pydantic_ok = False
    assert pydantic_ok is ok, f"Pydantic {'rejected' if ok else 'accepted'} {def_name}"
    assert (not errors) is ok, f"JSON Schema {'rejected' if ok else 'accepted'} {def_name}: {errors[:1]}"
    if ok:
        # Serializing and re-validating must be lossless.
        wire = parsed.model_dump(mode="json", exclude_unset=True)
        assert model.model_validate(wire) == parsed
        assert not list(_validator(def_name).iter_errors(wire))


def test_envelope_payloads_match_registered_types() -> None:
    data = json.loads((SAMPLES / "envelope.json").read_text(encoding="utf-8"))
    for item in data["valid"]:
        env = envelope.Envelope.model_validate(item)
        payload = payloads.parse_payload(env)
        assert isinstance(payload, MESSAGE_TYPES[env.type])

"""Dotted path reads into normalized telemetry dicts (Section 7.5)."""

from __future__ import annotations

import re
from typing import Any

_RESOURCE = re.compile(r"^resources\[id=([^\]]+)\]\.(.+)$")


def read_path(frame: dict[str, Any], path: str) -> Any:
    if path.startswith("resources["):
        match = _RESOURCE.match(path)
        if match is None:
            return None
        resource_id, tail = match.group(1), match.group(2)
        resources = frame.get("resources")
        if not isinstance(resources, list):
            return None
        row = next((r for r in resources if isinstance(r, dict) and r.get("id") == resource_id), None)
        if row is None:
            return None
        if tail == "ratio":
            amount, capacity = row.get("amount"), row.get("capacity")
            if (
                not isinstance(amount, (int, float))
                or not isinstance(capacity, (int, float))
                or capacity == 0
            ):
                return None
            return amount / capacity
        return _walk(row, tail.split("."))
    return _walk(frame, path.split("."))


def _walk(value: Any, parts: list[str]) -> Any:
    current = value
    for part in parts:
        if not part:
            return None
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current

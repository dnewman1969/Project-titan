"""Parse KSP `settings.cfg` key blocks into control bindings (Section 7.7)."""

from __future__ import annotations

import re
from pathlib import Path

from titan_sdk_games.types import ControlBindingDTO

_BLOCK_START = re.compile(r"^([A-Z0-9_]+)\s*$")
_ASSIGN = re.compile(r"^\s*(primary|secondary)\s*=\s*(\S+)\s*$")


_ACTION_MAP: dict[str, tuple[str, str, str]] = {
    "STAGE": ("ksp.stage", "Stage", "irreversible"),
    "THROTTLE": ("ksp.throttle", "Throttle", "continuous"),
    "GEAR": ("ksp.gear", "Landing gear", "discrete"),
    "BRAKES": ("ksp.brakes", "Brakes", "continuous"),
    "RCS": ("ksp.rcs", "RCS toggle", "discrete"),
    "SAS": ("ksp.sas", "SAS toggle", "discrete"),
}


def parse_ksp_settings_cfg(path: Path) -> list[ControlBindingDTO]:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    bindings: list[ControlBindingDTO] = []
    i = 0
    while i < len(lines):
        header = _BLOCK_START.match(lines[i].strip())
        if header is None or i + 1 >= len(lines) or lines[i + 1].strip() != "{":
            i += 1
            continue
        block_name = header.group(1)
        i += 2
        body: list[str] = []
        depth = 1
        while i < len(lines) and depth > 0:
            line = lines[i]
            if line.strip() == "{":
                depth += 1
            elif line.strip() == "}":
                depth -= 1
                if depth == 0:
                    break
            else:
                body.append(line)
            i += 1
        mapped = _ACTION_MAP.get(block_name)
        if mapped is not None:
            action_id, label, action_class = mapped
            for body_line in body:
                prim = _ASSIGN.match(body_line)
                if prim is None:
                    continue
                bindings.append(
                    ControlBindingDTO(
                        action_id=action_id,
                        action_label=label,
                        context="flight",
                        device="keyboard",
                        binding={"key": prim.group(2), "mods": []},
                        action_class=action_class,  # type: ignore[arg-type]
                        source="config_file",
                    )
                )
        i += 1
    return bindings

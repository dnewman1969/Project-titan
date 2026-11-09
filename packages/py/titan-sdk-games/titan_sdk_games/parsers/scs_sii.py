"""Parse SCS `controls.sii` mix entries into control bindings."""

from __future__ import annotations

import re
from pathlib import Path

from titan_sdk_games.types import ControlBindingDTO

_MIX_LINE = re.compile(
    r'config_lines\[\d+\]:\s*"(?P<action>[^"]+)"\s*"(?P<device>[^"]+)"\s*"(?P<binding>[^"]*)"',
)

_ACTION_MAP: dict[str, tuple[str, str, str]] = {
    "shift_up": ("scs.shift_up", "Shift up", "discrete"),
    "shift_down": ("scs.shift_down", "Shift down", "discrete"),
    "pause": ("scs.pause", "Pause", "menu"),
    "hblight": ("scs.headlights", "Headlights", "discrete"),
    "wipers": ("scs.wipers", "Wipers", "discrete"),
    "horn": ("scs.horn", "Horn", "discrete"),
    "engine_brake": ("scs.engine_brake", "Engine brake", "discrete"),
    "cruise_control": ("scs.cruise_control", "Cruise control", "discrete"),
}


def parse_scs_controls_sii(path: Path) -> list[ControlBindingDTO]:
    text = path.read_text(encoding="utf-8", errors="replace")
    bindings: list[ControlBindingDTO] = []
    for match in _MIX_LINE.finditer(text):
        action = match.group("action")
        device_raw = match.group("device").lower()
        binding_raw = match.group("binding")
        mapped = _ACTION_MAP.get(action)
        if mapped is None:
            continue
        action_id, label, action_class = mapped
        device = _map_device(device_raw)
        binding = _map_binding(device, binding_raw)
        bindings.append(
            ControlBindingDTO(
                action_id=action_id,
                action_label=label,
                context="driving",
                device=device,  # type: ignore[arg-type]
                binding=binding,
                action_class=action_class,  # type: ignore[arg-type]
                source="config_file",
            )
        )
    return bindings


def _map_device(raw: str) -> str:
    if raw in {"keyboard", "mouse", "gamepad", "joystick", "hotas", "wheel"}:
        return raw
    if raw.startswith("joy"):
        return "gamepad"
    return "keyboard"


def _map_binding(device: str, raw: str) -> dict[str, object]:
    if device == "keyboard":
        return {"key": raw, "mods": []}
    if device == "mouse":
        return {"button": raw, "mods": []}
    return {"control": raw}

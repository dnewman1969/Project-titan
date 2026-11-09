"""Load `titan.games` entry points without importing game packages by name from core."""

from __future__ import annotations

import sys
from collections.abc import Callable
from importlib import import_module
from importlib.metadata import EntryPoint, entry_points
from typing import cast

from titan_sdk_games.adapter import GameAdapter

_GROUP = "titan.games"


def _entry_point_map() -> dict[str, Callable[[], type[GameAdapter]]]:
    selected = entry_points()
    eps: list[EntryPoint]
    if hasattr(selected, "select"):
        eps = list(selected.select(group=_GROUP))
    else:
        eps = list(cast(dict[str, list[EntryPoint]], selected).get(_GROUP, []))
    out: dict[str, Callable[[], type[GameAdapter]]] = {}
    for ep in eps:
        name = ep.name
        target = ep.value

        def _resolve(value: str = target, ep_name: str = name) -> type[GameAdapter]:
            module_name, attr = value.split(":", 1)
            module = import_module(module_name)
            obj = getattr(module, attr)
            adapter_cls: type[GameAdapter]
            if isinstance(obj, type) and issubclass(obj, GameAdapter):
                adapter_cls = obj
            elif callable(obj):
                adapter_cls = cast(type[GameAdapter], obj())
            else:
                raise TypeError(f"entry point {ep_name!r} did not resolve to GameAdapter")
            adapter_cls.entry_point = ep_name
            adapter_cls.load_manifest()
            return adapter_cls

        out[name] = _resolve
    return out


def load_adapters() -> dict[str, type[GameAdapter]]:
    adapters: dict[str, type[GameAdapter]] = {}
    for name, factory in _entry_point_map().items():
        try:
            adapters[name] = factory()
        except Exception as exc:
            sys.stderr.write(f"warn: skipping titan.games entry {name!r}: {exc!r}\n")
    return adapters

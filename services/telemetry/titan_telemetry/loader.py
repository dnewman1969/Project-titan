"""Load a game adapter and rules path by slug (Section 7.1)."""

from __future__ import annotations

from pathlib import Path

from titan_sdk_games.adapter import GameAdapter
from titan_sdk_games.loader import load_adapters


def adapter_for(slug: str) -> type[GameAdapter]:
    adapters = load_adapters()
    if slug not in adapters:
        raise KeyError(f"unknown game slug {slug!r}")
    return adapters[slug]


def rules_path(adapter_cls: type[GameAdapter]) -> Path:
    manifest = adapter_cls.load_manifest()
    root = adapter_cls.manifest_path().parent
    return root / manifest.event_rules

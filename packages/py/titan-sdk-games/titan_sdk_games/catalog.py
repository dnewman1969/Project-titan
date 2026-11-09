"""Registry of installed game adapters (no database coupling)."""

from __future__ import annotations

from dataclasses import dataclass, field

from titan_sdk_games.adapter import GameAdapter
from titan_sdk_games.loader import load_adapters


@dataclass
class GameCatalog:
    adapters: dict[str, type[GameAdapter]] = field(default_factory=load_adapters)

    def reload(self) -> None:
        self.adapters = load_adapters()

    def by_slug(self, slug: str) -> tuple[str, type[GameAdapter]] | None:
        for ep_name, adapter_cls in self.adapters.items():
            if adapter_cls.load_manifest().id == slug:
                return ep_name, adapter_cls
        return None

    def get(self, slug: str) -> type[GameAdapter] | None:
        row = self.by_slug(slug)
        return row[1] if row else None

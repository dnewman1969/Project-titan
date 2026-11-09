from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from titan_sdk_games.types import DiscoveryContext


@dataclass(frozen=True)
class StoreInstall:
    store: Literal["steam", "epic", "gog", "standalone"]
    install_path: str
    executable_path: str
    app_id: str
    build_id: str | None
    name: str | None


class StoreScanner(ABC):
    name: Literal["steam", "epic", "gog", "standalone"]

    @abstractmethod
    def scan(self, ctx: DiscoveryContext) -> list[StoreInstall]: ...


def scan_all_stores(ctx: DiscoveryContext, stores: list[str]) -> list[StoreInstall]:
    from titan_sdk_games.discovery.epic import EpicScanner
    from titan_sdk_games.discovery.gog import GogScanner
    from titan_sdk_games.discovery.standalone import StandaloneScanner
    from titan_sdk_games.discovery.steam import SteamScanner

    scanners: dict[str, StoreScanner] = {
        "steam": SteamScanner(),
        "epic": EpicScanner(),
        "gog": GogScanner(),
        "standalone": StandaloneScanner(),
    }
    found: list[StoreInstall] = []
    for store in stores:
        scanner = scanners.get(store)
        if scanner is None:
            continue
        found.extend(scanner.scan(ctx))
    return found

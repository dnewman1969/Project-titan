"""Store scanners (Section 2.10)."""

from titan_sdk_games.discovery.base import StoreScanner, scan_all_stores
from titan_sdk_games.discovery.epic import EpicScanner
from titan_sdk_games.discovery.gog import GogScanner
from titan_sdk_games.discovery.standalone import StandaloneScanner
from titan_sdk_games.discovery.steam import SteamScanner

__all__ = [
    "EpicScanner",
    "GogScanner",
    "StandaloneScanner",
    "SteamScanner",
    "StoreScanner",
    "scan_all_stores",
]

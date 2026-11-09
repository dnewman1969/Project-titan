"""GameAdapter ABC, manifest model, discovery scanners, rule engine types and adapter test harness."""

from titan_sdk_games.adapter import AdapterConfig, GameAdapter, NotSupported, RawFrame
from titan_sdk_games.catalog import GameCatalog
from titan_sdk_games.harness import AdapterHarness
from titan_sdk_games.loader import load_adapters
from titan_sdk_games.manifest import GameManifest
from titan_sdk_games.types import (
    Consent,
    ControlBindingDTO,
    DetectedInstall,
    DiscoveryContext,
    IntegrationStatus,
)

__all__ = [
    "AdapterConfig",
    "AdapterHarness",
    "Consent",
    "ControlBindingDTO",
    "DetectedInstall",
    "DiscoveryContext",
    "GameAdapter",
    "GameCatalog",
    "GameManifest",
    "IntegrationStatus",
    "NotSupported",
    "RawFrame",
    "load_adapters",
]

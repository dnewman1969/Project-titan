from __future__ import annotations

from pathlib import Path

from titan_core.protocol.telemetry import TelemetryFrame
from titan_sdk_games.adapter import AdapterConfig, GameAdapter, RawFrame
from titan_sdk_games.profiles import GameProfile
from titan_sdk_games.types import IntegrationStatus


class TestgameAdapter(GameAdapter):
    @classmethod
    def manifest_path(cls) -> Path:
        return Path(__file__).resolve().parent.parent / "titan-game.yaml"

    def check_integration(self, profile: GameProfile) -> IntegrationStatus:
        del profile
        return IntegrationStatus(status="installed", details={"test": True})

    async def connect(self, profile: GameProfile, cfg: AdapterConfig) -> None:
        del profile, cfg

    def normalize(self, raw: RawFrame) -> TelemetryFrame:
        del raw
        raise NotImplementedError

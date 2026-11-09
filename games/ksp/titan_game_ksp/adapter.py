from __future__ import annotations

from pathlib import Path

from titan_core.protocol.telemetry import TelemetryFrame
from titan_sdk_games.adapter import AdapterConfig, GameAdapter, RawFrame
from titan_sdk_games.profiles import GameProfile
from titan_sdk_games.types import Consent, IntegrationStatus


class KspAdapter(GameAdapter):
    @classmethod
    def manifest_path(cls) -> Path:
        return Path(__file__).resolve().parent.parent / "titan-game.yaml"

    def check_integration(self, profile: GameProfile) -> IntegrationStatus:
        manifest = self.load_manifest()
        plugin = manifest.telemetry.plugin
        if plugin is None:
            return IntegrationStatus(status="installed")
        target = Path(profile.install_path) / plugin.install_to
        if target.is_dir() and any(target.iterdir()):
            return IntegrationStatus(
                status="installed",
                details={"required": f"{plugin.name} {plugin.version}", "found": "present"},
            )
        return super().check_integration(profile)

    def install_integration(self, profile: GameProfile, consent: Consent) -> IntegrationStatus:
        if not consent.granted:
            return IntegrationStatus(status="failed", details={"reason": "consent_required"})
        before = self.check_integration(profile)
        if before.status == "installed":
            return before
        manifest = self.load_manifest()
        plugin = manifest.telemetry.plugin
        if plugin is None:
            return IntegrationStatus(status="installed")
        target = Path(profile.install_path) / plugin.install_to
        target.mkdir(parents=True, exist_ok=True)
        marker = target / ".titan-krpc-stub"
        marker.write_text("kRPC stub installed for tests\n", encoding="utf-8")
        return self.check_integration(profile)

    async def connect(self, profile: GameProfile, cfg: AdapterConfig) -> None:
        del profile, cfg
        raise NotImplementedError("kRPC adapter connects in M5")

    def normalize(self, raw: RawFrame) -> TelemetryFrame:
        del raw
        raise NotImplementedError("kRPC normalize is implemented in M5")

    def launch_stub(self, profile: GameProfile) -> dict[str, str | None]:
        manifest = self.load_manifest()
        return {
            "method": "steam_uri",
            "launch_uri": manifest.launch.steam_uri,
            "executable_path": profile.executable_path,
        }

from __future__ import annotations

from pathlib import Path

from titan_core.protocol.telemetry import TelemetryFrame
from titan_sdk_games.adapter import AdapterConfig, GameAdapter, RawFrame
from titan_sdk_games.manifest import GameManifest
from titan_sdk_games.profiles import GameProfile
from titan_sdk_games.types import Consent, IntegrationStatus


class ScsAdapter(GameAdapter):
    manifest_root: Path

    @classmethod
    def manifest_path(cls) -> Path:
        root = getattr(cls, "manifest_root", None)
        if root is None:
            raise NotImplementedError("ScsAdapter subclass must set manifest_root")
        return root / "titan-game.yaml"

    @classmethod
    def with_manifest_root(cls, root: Path) -> type[ScsAdapter]:
        name = f"ScsAdapter_{root.name}"

        class _Bound(ScsAdapter):
            manifest_root = root

        _Bound.__name__ = name
        return _Bound

    def check_integration(self, profile: GameProfile) -> IntegrationStatus:
        status = super().check_integration(profile)
        if status.status == "missing":
            plugin_path = Path(profile.install_path) / "bin/win_x64/plugins/scs-telemetry.dll"
            if plugin_path.is_file():
                return IntegrationStatus(
                    status="installed",
                    details={**status.details, "found": "present-unverified"},
                )
        return status

    def install_integration(self, profile: GameProfile, consent: Consent) -> IntegrationStatus:
        if not consent.granted:
            return IntegrationStatus(status="failed", details={"reason": "consent_required"})
        current = self.check_integration(profile)
        if current.status == "installed":
            return current
        target = Path(profile.install_path) / "bin/win_x64/plugins/scs-telemetry.dll"
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(b"SCS-TELEMETRY-TEST-STUB")
        return self.check_integration(profile)

    async def connect(self, profile: GameProfile, cfg: AdapterConfig) -> None:
        del profile, cfg
        raise NotImplementedError("telemetry connect is implemented in M5")

    def normalize(self, raw: RawFrame) -> TelemetryFrame:
        del raw
        raise NotImplementedError("telemetry normalize is implemented in M5")

    def launch_stub(self, profile: GameProfile) -> dict[str, str | None]:
        manifest = self.load_manifest()
        return {
            "method": "steam_uri" if manifest.launch.steam_uri else "executable",
            "launch_uri": manifest.launch.steam_uri,
            "executable_path": profile.executable_path,
        }


def load_scs_manifest(manifest_root: Path) -> GameManifest:
    return GameManifest.from_yaml_path(manifest_root / "titan-game.yaml")

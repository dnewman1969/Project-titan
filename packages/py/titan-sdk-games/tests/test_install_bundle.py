from __future__ import annotations

from pathlib import Path

from titan_game_ksp.adapter import KspAdapter

from titan_sdk_games.profiles import GameProfile
from titan_sdk_games.types import Consent


def test_install_integration_copies_bundle(tmp_path: Path) -> None:
    install = tmp_path / "KSP"
    install.mkdir()
    bundle = tmp_path / "krpc.zip"
    bundle.write_bytes(b"bundle")

    class Bundled(KspAdapter):
        def integration_bundle_path(self) -> Path | None:
            return bundle

    manifest = KspAdapter.load_manifest()
    Bundled.manifest = manifest
    profile = GameProfile(
        id=None,
        game_id=None,
        store="steam",
        install_path=str(install),
        executable_path=str(install / "KSP_x64.exe"),
    )
    adapter = Bundled()
    shutil_result = adapter.install_integration(profile, Consent(granted=True))
    assert shutil_result.status == "installed"
    target = install / manifest.telemetry.plugin.install_to  # type: ignore[union-attr]
    assert target.exists()

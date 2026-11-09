from __future__ import annotations

import hashlib
from pathlib import Path

from titan_game_ksp.adapter import KspAdapter

from titan_sdk_games.catalog import GameCatalog
from titan_sdk_games.loader import load_adapters
from titan_sdk_games.profiles import GameProfile
from titan_sdk_games.types import Consent


def test_catalog_get_by_slug() -> None:
    catalog = GameCatalog(adapters=load_adapters())
    row = catalog.by_slug("ksp")
    assert row is not None
    assert catalog.get("ksp") is not None


def test_parse_default_controls(tmp_path: Path) -> None:
    install = tmp_path / "KSP"
    install.mkdir()
    profile = GameProfile(
        id=None,
        game_id=None,
        store="standalone",
        install_path=str(install),
        executable_path=str(install / "KSP_x64.exe"),
    )
    bindings = KspAdapter().parse_controls(profile)
    assert bindings and bindings[0].action_id == "ksp.stage"


def test_integration_refuses_without_consent(tmp_path: Path) -> None:
    install = tmp_path / "KSP"
    install.mkdir()
    profile = GameProfile(
        id=None,
        game_id=None,
        store="steam",
        install_path=str(install),
        executable_path=str(install / "KSP_x64.exe"),
    )
    result = KspAdapter().install_integration(profile, Consent(granted=False))
    assert result.status == "failed"


def test_hash_mismatch_reports_outdated(tmp_path: Path) -> None:
    install = tmp_path / "ets2"
    plugin = install / "bin" / "win_x64" / "plugins" / "scs-telemetry.dll"
    plugin.parent.mkdir(parents=True)
    plugin.write_bytes(b"wrong")
    from titan_game_ets2.adapter import Ets2Adapter

    prior = Ets2Adapter.manifest
    manifest = Ets2Adapter.load_manifest()
    assert manifest.telemetry.plugin is not None
    manifest.telemetry.plugin.sha256 = hashlib.sha256(b"right").hexdigest()
    Ets2Adapter.manifest = manifest
    try:
        profile = GameProfile(
            id=None,
            game_id=None,
            store="steam",
            install_path=str(install),
            executable_path=str(install / "game.exe"),
        )
        status = Ets2Adapter().check_integration(profile)
        assert status.status == "outdated"
    finally:
        Ets2Adapter.manifest = prior

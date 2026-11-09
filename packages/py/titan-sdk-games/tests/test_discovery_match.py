from __future__ import annotations

from pathlib import Path

from titan_game_ksp.adapter import KspAdapter

from titan_sdk_games.discovery.steam import SteamScanner
from titan_sdk_games.types import DiscoveryContext


def test_detect_skips_unmatched_steam_app_id(tmp_path: Path) -> None:
    lib = tmp_path / "steam"
    steamapps = lib / "steamapps"
    steamapps.mkdir(parents=True)
    common = lib / "common" / "Other"
    common.mkdir(parents=True)
    (common / "game.exe").write_bytes(b"MZ")
    manifest = (
        '"AppState"\n{\n\t"appid"\t\t"1"\n\t"buildid"\t\t"1"\n\t"installdir"\t\t"Other"\n}\n'
    )
    (steamapps / "appmanifest_1.acf").write_text(manifest, encoding="utf-8")
    ctx = DiscoveryContext(platform="linux", steam_libraries=[lib])
    assert KspAdapter.detect(ctx) == []


def test_steam_scanner_uses_steam_path_env(tmp_path: Path) -> None:
    lib = tmp_path / "Steam"
    steamapps = lib / "steamapps"
    steamapps.mkdir(parents=True)
    (steamapps / "libraryfolders.vdf").write_text('"libraryfolders"\n{\n}\n', encoding="utf-8")
    common = lib / "common" / "Game"
    common.mkdir(parents=True)
    (common / "a.exe").write_bytes(b"MZ")
    (steamapps / "appmanifest_2.acf").write_text(
        '"AppState"\n{\n"appid" "2"\n"installdir" "Game"\n}\n',
        encoding="utf-8",
    )
    ctx = DiscoveryContext(platform="windows", env={"STEAM_PATH": str(lib)})
    found = SteamScanner().scan(ctx)
    assert len(found) == 1

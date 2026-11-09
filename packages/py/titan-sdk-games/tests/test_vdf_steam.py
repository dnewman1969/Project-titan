from __future__ import annotations

from pathlib import Path

from titan_game_ets2.adapter import Ets2Adapter

from titan_sdk_games.discovery.steam import SteamScanner
from titan_sdk_games.types import DiscoveryContext

FIXTURES = Path(__file__).resolve().parent / "fixtures"
STEAM = FIXTURES / "steam"


def test_steam_scanner_reads_acf(tmp_path: Path) -> None:
    lib = tmp_path / "steam"
    steamapps = lib / "steamapps"
    steamapps.mkdir(parents=True)
    (steamapps / "libraryfolders.vdf").write_text(
        (STEAM / "libraryfolders.vdf").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    common = lib / "common" / "Euro Truck Simulator 2"
    common.mkdir(parents=True)
    (common / "eurotrucks2.exe").write_bytes(b"MZ")
    (steamapps / "appmanifest_227300.acf").write_text(
        (STEAM / "steamapps" / "appmanifest_227300.acf").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    ctx = DiscoveryContext(platform="linux", steam_libraries=[lib])
    installs = SteamScanner().scan(ctx)
    assert len(installs) == 1
    assert installs[0].app_id == "227300"
    assert installs[0].build_id == "12345678"


def test_ets2_detect_from_fixture(tmp_path: Path) -> None:
    lib = tmp_path / "steam"
    steamapps = lib / "steamapps"
    steamapps.mkdir(parents=True)
    (steamapps / "libraryfolders.vdf").write_text('""\n{\n}\n', encoding="utf-8")
    common = lib / "common" / "Euro Truck Simulator 2"
    common.mkdir(parents=True)
    (common / "eurotrucks2.exe").write_bytes(b"MZ")
    manifest = (
        '"AppState"\n{\n\t"appid"\t\t"227300"\n\t"buildid"\t\t"42"\n\t"installdir"\t\t"Euro Truck Simulator 2"\n}\n'
    )
    (steamapps / "appmanifest_227300.acf").write_text(manifest, encoding="utf-8")
    ctx = DiscoveryContext(platform="linux", steam_libraries=[lib])
    hits = Ets2Adapter.detect(ctx)
    assert len(hits) == 1
    assert hits[0].game_slug == "ets2"

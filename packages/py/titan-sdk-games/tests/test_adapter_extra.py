from __future__ import annotations

import json
from pathlib import Path

from titan_game_ets2.adapter import Ets2Adapter

from titan_sdk_games.discovery.epic import EpicScanner
from titan_sdk_games.discovery.gog import GogScanner
from titan_sdk_games.discovery.standalone import StandaloneScanner
from titan_sdk_games.harness import AdapterHarness
from titan_sdk_games.profiles import GameProfile
from titan_sdk_games.types import Consent, DiscoveryContext


def test_standalone_scanner_and_detect(tmp_path: Path) -> None:
    exe = tmp_path / "bin" / "win_x64" / "eurotrucks2.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ")
    ctx = DiscoveryContext(platform="linux", extra_paths=[exe])
    hits = StandaloneScanner().scan(ctx)
    assert hits
    detected = Ets2Adapter.detect(DiscoveryContext(platform="linux", extra_paths=[exe.parent.parent]))
    assert any(d.game_slug == "ets2" for d in detected)


def test_epic_scanner_reads_item(tmp_path: Path) -> None:
    manifests = tmp_path / "Manifests"
    manifests.mkdir()
    item = {
        "CatalogItemId": "Sugar",
        "InstallLocation": str(tmp_path / "Game"),
        "LaunchExecutable": "game.exe",
        "DisplayName": "Demo",
        "AppVersionString": "9",
    }
    (tmp_path / "Game").mkdir()
    (tmp_path / "Game" / "game.exe").write_bytes(b"MZ")
    (manifests / "Game.item").write_text(json.dumps(item), encoding="utf-8")
    ctx = DiscoveryContext(platform="windows", epic_manifest_dirs=[manifests])
    found = EpicScanner().scan(ctx)
    assert len(found) == 1
    assert found[0].app_id == "Sugar"


def test_gog_scanner_reads_goggame(tmp_path: Path) -> None:
    root = tmp_path / "123"
    root.mkdir()
    data = {"productId": "abc", "name": "GOG Game", "playTasks": [{"path": "run.exe"}]}
    (root / "goggame.json").write_text(json.dumps(data), encoding="utf-8")
    (root / "run.exe").write_bytes(b"MZ")
    ctx = DiscoveryContext(platform="linux", gog_install_roots=[tmp_path])
    found = GogScanner().scan(ctx)
    assert found and found[0].store == "gog"


def test_scs_integration_install_and_launch_stub(tmp_path: Path) -> None:
    install = tmp_path / "ets2"
    install.mkdir()
    profile = GameProfile(
        id=None,
        game_id=None,
        store="steam",
        install_path=str(install),
        executable_path=str(install / "eurotrucks2.exe"),
    )
    adapter = Ets2Adapter()
    status = adapter.install_integration(profile, Consent(granted=True))
    assert status.status == "installed"
    launch = adapter.launch_stub(profile)
    assert launch["method"] == "steam_uri"


def test_harness_counts_frames(tmp_path: Path) -> None:
    ndjson = tmp_path / "frames.ndjson"
    ndjson.write_text('{"t": 1}\n{"t": 2}\n', encoding="utf-8")

    class Stub(Ets2Adapter):
        def normalize(self, raw):  # type: ignore[no-untyped-def]
            del raw
            return object()

    result = AdapterHarness(Stub()).run_ndjson(ndjson)
    assert result.frames == 2

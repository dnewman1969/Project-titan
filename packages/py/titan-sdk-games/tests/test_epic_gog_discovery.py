from __future__ import annotations

import json
import sys
import types
from pathlib import Path

from titan_game_ksp.adapter import KspAdapter

from titan_sdk_games.discovery.epic import EpicScanner
from titan_sdk_games.discovery.gog import GogScanner
from titan_sdk_games.discovery.gog_registry import (
    GogRegistryInstall,
    _registry_path,
    list_gog_registry_installs,
)
from titan_sdk_games.types import DiscoveryContext


def test_registry_path_normalizes_windows_drive() -> None:
    path = _registry_path("D:/GOG Games/Kerbal")
    assert str(path).startswith("D:\\")


def test_epic_resolves_launch_exe_basename(tmp_path: Path) -> None:
    manifests = tmp_path / "Manifests"
    manifests.mkdir()
    install = tmp_path / "Game"
    sub = install / "win64"
    sub.mkdir(parents=True)
    (sub / "Launch.exe").write_bytes(b"MZ")
    item = {
        "CatalogItemId": "abc",
        "InstallLocation": str(install),
        "LaunchExecutable": "win64/Launch.exe",
        "DisplayName": "Demo",
    }
    (manifests / "game.item").write_text(json.dumps(item), encoding="utf-8")
    found = EpicScanner().scan(DiscoveryContext(platform="windows", epic_manifest_dirs=[manifests]))
    assert found and found[0].executable_path.endswith("Launch.exe")


def test_epic_skips_incomplete_install(tmp_path: Path) -> None:
    manifests = tmp_path / "Manifests"
    manifests.mkdir()
    install = tmp_path / "KSP"
    install.mkdir()
    item = {
        "CatalogItemId": "84686da593b24598803ffbe7f9b1bb5e",
        "InstallLocation": str(install),
        "LaunchExecutable": "KSP_x64.exe",
        "bIsIncompleteInstall": True,
    }
    (manifests / "ksp.item").write_text(json.dumps(item), encoding="utf-8")
    assert EpicScanner().scan(DiscoveryContext(platform="windows", epic_manifest_dirs=[manifests])) == []


def test_epic_ksp_detected_by_catalog_id(tmp_path: Path) -> None:
    manifests = tmp_path / "Manifests"
    manifests.mkdir()
    install = tmp_path / "KerbalSpaceProgram"
    install.mkdir()
    (install / "KSP_x64.exe").write_bytes(b"MZ")
    item = {
        "CatalogItemId": "84686da593b24598803ffbe7f9b1bb5e",
        "AppName": "KerbalSpaceProgram",
        "InstallLocation": str(install),
        "LaunchExecutable": "KSP_x64.exe",
        "DisplayName": "Kerbal Space Program",
        "AppVersionString": "1.12",
    }
    (manifests / "ksp.item").write_text(json.dumps(item), encoding="utf-8")
    ctx = DiscoveryContext(platform="windows", epic_manifest_dirs=[manifests])
    hits = KspAdapter.detect(ctx, stores=["epic"])
    assert len(hits) == 1
    assert hits[0].store == "epic"


def test_gog_registry_install(monkeypatch, tmp_path: Path) -> None:
    install = tmp_path / "Kerbal Space Program"
    install.mkdir()
    exe = install / "KSP_x64.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setattr("os.name", "nt")
    winreg = types.SimpleNamespace(HKEY_LOCAL_MACHINE=1)

    class ProductKey:
        def __init__(self, data: dict[str, str]) -> None:
            self._data = data

        def __enter__(self) -> ProductKey:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    class GamesKey:
        def __enter__(self) -> GamesKey:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def fake_open(hive: int, path: str) -> ProductKey | GamesKey:
        if path.endswith("Games"):
            return GamesKey()
        if "1429864849" in path:
            key = ProductKey(
                {
                    "path": str(install),
                    "exe": str(exe),
                    "gameName": "Kerbal Space Program",
                    "BUILDID": "gog-1",
                }
            )

            def query_value(name: str) -> tuple[str, int]:
                if name not in key._data:
                    raise OSError
                return key._data[name], 1

            key.QueryValueEx = query_value  # type: ignore[method-assign]
            return key
        raise OSError

    winreg.OpenKey = fake_open
    winreg.QueryInfoKey = lambda _key: (1, 0, 0, 0, 0)
    winreg.EnumKey = lambda _key, index: "1429864849" if index == 0 else ""
    winreg.QueryValueEx = lambda key, name: key.QueryValueEx(name)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "winreg", winreg)

    assert len(list_gog_registry_installs()) == 1
    assert list_gog_registry_installs()[0].product_id == "1429864849"
    monkeypatch.setattr(
        "titan_sdk_games.discovery.gog.list_gog_registry_installs",
        lambda: [
            GogRegistryInstall(
                product_id="1429864849",
                install_path=install,
                executable_path=exe,
                game_name="Kerbal Space Program",
                build_id="gog-1",
            )
        ],
    )
    ctx = DiscoveryContext(platform="windows", gog_install_roots=[])
    found = GogScanner().scan(ctx)
    assert len(found) == 1
    assert found[0].app_id == "1429864849"
    ksp = KspAdapter.detect(ctx, stores=["gog"])
    assert len(ksp) == 1

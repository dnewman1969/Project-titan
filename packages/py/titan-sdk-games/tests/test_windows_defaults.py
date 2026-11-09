"""Windows discovery defaults."""

from __future__ import annotations

from pathlib import Path

from titan_sdk_games.discovery.gog_registry import GogRegistryInstall, list_gog_registry_installs
from titan_sdk_games.discovery.windows_defaults import (
    _steam_registry_candidates,
    enrich_discovery_context,
)


def test_enrich_linux_has_no_steam_libs_by_default(tmp_path: Path) -> None:
    extra = tmp_path / "scan"
    extra.mkdir()
    ctx = enrich_discovery_context(platform="linux", extra_paths=[extra])
    assert ctx.platform == "linux"
    assert ctx.extra_paths == [extra]
    assert ctx.steam_libraries == []


def test_enrich_windows_merges_extra_paths(monkeypatch) -> None:
    monkeypatch.setenv("STEAM_PATH", r"C:\Steam")
    ctx = enrich_discovery_context(platform="windows", extra_paths=[])
    assert any(p.name == "Steam" or str(p) == r"C:\Steam" for p in ctx.steam_libraries)
    assert ctx.env.get("STEAM_PATH") == r"C:\Steam"


def test_steam_libraryfolders_expands_secondary_root(tmp_path, monkeypatch) -> None:
    steam = tmp_path / "Steam"
    steam.mkdir()
    secondary = tmp_path / "SteamLibrary"
    secondary.mkdir()
    vdf_dir = steam / "steamapps"
    vdf_dir.mkdir()
    vdf_dir.joinpath("libraryfolders.vdf").write_text(
        f'"libraryfolders"\n{{\n\t"1"\n\t{{\n\t\t"path"\t\t"{secondary}"\n\t}}\n}}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("STEAM_PATH", str(steam))
    ctx = enrich_discovery_context(platform="windows", extra_paths=[])
    lib_strs = [str(p) for p in ctx.steam_libraries]
    assert str(steam) in lib_strs
    assert str(secondary) in lib_strs


def test_enrich_windows_epic_manifest_and_common_scan_paths(tmp_path: Path) -> None:
    programdata = tmp_path / "ProgramData"
    programdata.mkdir()
    steam = tmp_path / "Steam"
    common = steam / "steamapps" / "common"
    common.mkdir(parents=True)
    ctx = enrich_discovery_context(
        platform="windows",
        extra_paths=[],
        env={"STEAM_PATH": str(steam), "PROGRAMDATA": str(programdata)},
    )
    primary = programdata / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    assert primary in ctx.epic_manifest_dirs
    assert len(ctx.epic_manifest_dirs) >= 2
    assert common in ctx.extra_paths


def test_steam_libraryfolders_multiple_entries(tmp_path: Path) -> None:
    steam = tmp_path / "Steam"
    steam.mkdir()
    lib_a = tmp_path / "LibA"
    lib_b = tmp_path / "LibB"
    lib_a.mkdir()
    lib_b.mkdir()
    vdf_dir = steam / "steamapps"
    vdf_dir.mkdir()
    vdf_dir.joinpath("libraryfolders.vdf").write_text(
        f'"libraryfolders"\n{{\n\t"1"\n\t{{\n\t\t"path"\t\t"{lib_a}"\n\t}}\n\t"2"\n\t{{\n\t\t"path"\t\t"{lib_b}"\n\t}}\n}}\n',
        encoding="utf-8",
    )
    ctx = enrich_discovery_context(platform="windows", env={"STEAM_PATH": str(steam)})
    lib_strs = {str(p) for p in ctx.steam_libraries}
    assert str(steam) in lib_strs
    assert str(lib_a) in lib_strs
    assert str(lib_b) in lib_strs


def test_default_gog_roots_include_registry_install(tmp_path: Path, monkeypatch) -> None:
    install = tmp_path / "Kerbal"
    install.mkdir()
    monkeypatch.setattr(
        "titan_sdk_games.discovery.gog_registry.list_gog_registry_installs",
        lambda: [
            GogRegistryInstall(
                product_id="1429864849",
                install_path=install,
                executable_path=None,
                game_name="KSP",
                build_id=None,
            )
        ],
    )
    from titan_sdk_games.discovery.windows_defaults import _default_gog_roots

    roots = _default_gog_roots()
    assert install in roots


def test_gog_registry_empty_off_windows(monkeypatch) -> None:
    monkeypatch.setattr("os.name", "posix")
    assert list_gog_registry_installs() == []


def test_enrich_windows_epic_manifest_includes_localappdata(tmp_path: Path) -> None:
    programdata = tmp_path / "ProgramData"
    localappdata = tmp_path / "LocalAppData"
    ctx = enrich_discovery_context(
        platform="windows",
        env={"PROGRAMDATA": str(programdata), "LOCALAPPDATA": str(localappdata)},
    )
    local_manifests = localappdata / "EpicGamesLauncher" / "Data" / "Manifests"
    assert local_manifests in ctx.epic_manifest_dirs


def test_steam_registry_candidates_dedupes(monkeypatch) -> None:
    import sys
    import types

    monkeypatch.setattr("os.name", "nt")
    winreg = types.SimpleNamespace(HKEY_CURRENT_USER=1, HKEY_LOCAL_MACHINE=2)
    monkeypatch.setitem(sys.modules, "winreg", winreg)

    def fake_read(_hive: int, _subkey: str, value_name: str) -> str | None:
        if value_name in {"SteamPath", "InstallPath"}:
            return r"C:\Games\Steam"
        return None

    monkeypatch.setattr(
        "titan_sdk_games.discovery.windows_defaults._read_registry_string",
        fake_read,
    )
    assert _steam_registry_candidates() == [r"C:\Games\Steam"]


def test_infer_steam_library_root_from_common_layout(tmp_path: Path) -> None:
    from titan_sdk_games.discovery.windows_defaults import _steam_library_root_from_layout

    common = tmp_path / "SteamLibrary" / "steamapps" / "common"
    common.mkdir(parents=True)
    assert _steam_library_root_from_layout(common) == tmp_path / "SteamLibrary"
    assert _steam_library_root_from_layout(tmp_path / "SteamLibrary") == tmp_path / "SteamLibrary"


def test_ksp_secondary_library_forward_slash_vdf_path(tmp_path: Path) -> None:
    from titan_game_ksp.adapter import KspAdapter

    primary = tmp_path / "Steam"
    secondary = tmp_path / "SteamLibrary"
    primary_steamapps = primary / "steamapps"
    primary_steamapps.mkdir(parents=True)
    secondary_steamapps = secondary / "steamapps"
    secondary_steamapps.mkdir(parents=True)
    forward = str(secondary).replace("\\", "/")
    (primary_steamapps / "libraryfolders.vdf").write_text(
        f'"libraryfolders"\n{{\n\t"1"\n\t{{\n\t\t"path"\t\t"{forward}"\n\t}}\n}}\n',
        encoding="utf-8",
    )
    ksp = secondary / "common" / "Kerbal Space Program"
    ksp.mkdir(parents=True)
    (ksp / "KSP_x64.exe").write_bytes(b"MZ")
    manifest = (
        '"AppState"\n{\n\t"appid"\t\t"220200"\n\t"buildid"\t\t"99"\n\t"installdir"\t\t"'
        'Kerbal Space Program"\n}\n'
    )
    (secondary_steamapps / "appmanifest_220200.acf").write_text(manifest, encoding="utf-8")
    ctx = enrich_discovery_context(platform="windows", env={"STEAM_PATH": str(primary)})
    assert any(str(secondary) == str(p) for p in ctx.steam_libraries)
    hits = KspAdapter.detect(ctx, stores=["steam"])
    assert len(hits) == 1
    assert hits[0].executable_path.endswith("KSP_x64.exe")


def test_steam_libraryfolders_ignores_missing_vdf(tmp_path: Path) -> None:
    steam = tmp_path / "Steam"
    steam.mkdir()
    ctx = enrich_discovery_context(platform="windows", env={"STEAM_PATH": str(steam)})
    assert [str(steam)] == [str(p) for p in ctx.steam_libraries]

"""Windows discovery defaults."""

from __future__ import annotations

from pathlib import Path

from titan_sdk_games.discovery.windows_defaults import enrich_discovery_context


def test_enrich_linux_has_no_steam_libs_by_default() -> None:
    ctx = enrich_discovery_context(platform="linux", extra_paths=[Path("/tmp")])
    assert ctx.platform == "linux"
    assert ctx.extra_paths == [Path("/tmp")]
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

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

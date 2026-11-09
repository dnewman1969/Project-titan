from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from titan_game_ksp.adapter import KspAdapter

from titan_sdk_games.adapter import NotSupported, RawFrame
from titan_sdk_games.catalog import GameCatalog
from titan_sdk_games.manifest import GameManifest
from titan_sdk_games.profiles import GameProfile
from titan_sdk_games.types import DiscoveryContext


def test_adapter_runtime_defaults() -> None:
    adapter = KspAdapter()
    frame = adapter.normalize  # not called
    del frame
    assert adapter.scene(type("F", (), {})()) == "unknown"  # type: ignore[arg-type]
    assert adapter.world_state_summary(type("F", (), {})()) == {}  # type: ignore[arg-type]
    assert adapter.tools() == []
    assert adapter.default_team() == {}
    assert adapter.detect_events(None, type("F", (), {})(), RawFrame({})) == []  # type: ignore[arg-type]
    with pytest.raises(NotSupported):
        adapter.action_space()
    with pytest.raises(NotSupported):

        async def run() -> None:
            await adapter.execute({})

        asyncio.run(run())


def test_parse_controls_from_settings_file(tmp_path: Path) -> None:
    install = tmp_path / "KSP"
    install.mkdir()
    (install / "settings.cfg").write_text(
        "STAGE\n{\n primary = Space\n}\n",
        encoding="utf-8",
    )
    profile = GameProfile(
        id=None,
        game_id=None,
        store="standalone",
        install_path=str(install),
        executable_path=str(install / "KSP_x64.exe"),
    )
    bindings = KspAdapter().parse_controls(profile)
    assert bindings and bindings[0].binding["key"] == "Space"


def test_catalog_reload_and_missing_slug() -> None:
    catalog = GameCatalog()
    catalog.reload()
    assert catalog.get("missing-slug") is None
    assert catalog.by_slug("missing-slug") is None


def test_manifest_validation_and_store_ids() -> None:
    manifest = GameManifest.from_yaml_path(KspAdapter.manifest_path())
    assert manifest.genre
    assert manifest.store_ids()["steam"]


def test_disconnect_is_noop() -> None:
    asyncio.run(KspAdapter().disconnect())


def test_detect_standalone_executable_match(tmp_path: Path) -> None:
    exe = tmp_path / "KSP_x64.exe"
    exe.write_bytes(b"MZ")
    ctx = DiscoveryContext(platform="linux", extra_paths=[exe])
    hits = KspAdapter.detect(ctx)
    assert hits and hits[0].store == "standalone"

from __future__ import annotations

from pathlib import Path

from titan_game_ksp.adapter import KspAdapter

from titan_sdk_games.profiles import GameProfile
from titan_sdk_games.types import Consent


def test_ksp_install_integration_idempotent(tmp_path: Path) -> None:
    install = tmp_path / "KSP"
    install.mkdir()
    profile = GameProfile(
        id=None,
        game_id=None,
        store="steam",
        install_path=str(install),
        executable_path=str(install / "KSP_x64.exe"),
    )
    adapter = KspAdapter()
    first = adapter.install_integration(profile, Consent(granted=True))
    assert first.status == "installed"
    second = adapter.install_integration(profile, Consent(granted=True))
    assert second.status == "installed"

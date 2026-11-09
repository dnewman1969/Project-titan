from __future__ import annotations

from titan_sdk_games.loader import load_adapters


def test_load_adapters_includes_shipped_games() -> None:
    adapters = load_adapters()
    slugs = {cls.load_manifest().id for cls in adapters.values()}
    assert {"ksp", "ets2", "ats"}.issubset(slugs)

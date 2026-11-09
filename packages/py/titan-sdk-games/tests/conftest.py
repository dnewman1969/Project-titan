from __future__ import annotations

import pytest
from titan_game_ets2.adapter import Ets2Adapter


@pytest.fixture(autouse=True)
def reset_ets2_manifest() -> None:
    Ets2Adapter.manifest = None
    yield
    Ets2Adapter.manifest = None

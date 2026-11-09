from __future__ import annotations

import pytest

from titan_sdk_games.vdf import parse_vdf, vdf_get_str


def test_parse_vdf_root_key_block() -> None:
    root = parse_vdf('"AppState"\n{\n"key" "value"\n}\n')
    assert vdf_get_str(root, "AppState", "key") == "value"


def test_parse_vdf_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_vdf("not-a-block")

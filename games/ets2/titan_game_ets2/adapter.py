from __future__ import annotations

from pathlib import Path

from titan_game_scs.adapter import ScsAdapter

_ROOT = Path(__file__).resolve().parent.parent


class Ets2Adapter(ScsAdapter):
    manifest_root = _ROOT

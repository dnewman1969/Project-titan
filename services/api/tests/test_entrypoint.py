from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import titan_api.__main__ as entry


def test_main_runs_uvicorn_on_loopback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: dict[str, Any] = {}
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(entry, "configure_logging", lambda *a, **k: calls.setdefault("logging", (a, k)))
    monkeypatch.setattr(entry.uvicorn, "run", lambda app, **kwargs: calls.setdefault("run", kwargs))
    entry.main()
    assert calls["run"] == {"host": "127.0.0.1", "port": 8765, "workers": 1, "log_config": None}
    assert calls["logging"][0] == ("titan-api",)

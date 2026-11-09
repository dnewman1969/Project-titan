"""Closed-loop play against the HIL driver (no game required)."""

from __future__ import annotations

import os
from uuid import UUID

import pytest

from titan_actions.drivers.hil_driver import hil_state
from titan_actions.executor import PlayExecutor
from titan_actions.play_env import PlaySettings


@pytest.fixture
def hil_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TITAN_PLAY_BACKEND", "hil")
    monkeypatch.setenv("TITAN_GAME_SLUG", "ksp")


def test_learn_and_play_hil_sequence(hil_env: None) -> None:
    """Event policy proposes ksp.throttle; executor applies via HIL state."""
    settings = PlaySettings.from_environ()
    sid = UUID(int=99)
    ex = PlayExecutor(session_id=sid, settings=settings)
    ok, err, _lat1 = ex.execute("ksp.throttle", {"throttle": 0.75})
    assert ok and err is None
    ok, err, _lat2 = ex.execute("ksp.stage", {})
    assert ok and err is None
    state = hil_state()
    assert state["ksp"]["throttle"] == 0.75
    assert state["ksp"]["stage_count"] == 1
    assert os.environ.get("TITAN_PLAY_BACKEND") == "hil"

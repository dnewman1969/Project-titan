"""SCS ViGEm / keyboard driver with injected mocks (cloud-safe)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from titan_actions.drivers.factory import build_driver
from titan_actions.drivers.scs_driver import VK_S, VK_W, ScsDriver
from titan_actions.executor import PlayExecutor
from titan_actions.play_env import PlaySettings


class FakePad:
    def __init__(self) -> None:
        self.left: list[float] = []
        self.right: list[float] = []
        self.updates = 0

    def left_trigger_float(self, *, value_float: float) -> None:
        self.left.append(value_float)

    def right_trigger_float(self, *, value_float: float) -> None:
        self.right.append(value_float)

    def update(self) -> None:
        self.updates += 1


def test_scs_vgamepad_brake_and_throttle_via_fake_pad() -> None:
    pad = FakePad()
    driver = ScsDriver(pad_factory=lambda: pad)
    ok, err = driver.execute("scs.brake", {"brake": 0.8})
    assert ok and err is None
    assert driver.mode == "vgamepad"
    assert pad.left == [0.8]
    assert pad.updates == 1

    ok, err = driver.execute("scs.throttle", {"throttle": 0.4})
    assert ok and err is None
    assert pad.right == [0.4]
    assert pad.updates == 2

    driver.reset()
    assert pad.left[-1] == 0.0
    assert pad.right[-1] == 0.0


def test_scs_keyboard_brake_and_throttle_via_injected_key_hold() -> None:
    holds: list[tuple[int, float]] = []

    def record(vk: int, *, hold_s: float) -> None:
        holds.append((vk, hold_s))

    driver = ScsDriver(prefer_keyboard=True, key_hold_fn=record)
    ok, err = driver.execute("scs.brake", {"brake": 0.5})
    assert ok and err is None
    assert driver.mode == "keyboard"
    assert holds == [(VK_S, 0.5)]

    ok, err = driver.execute("scs.throttle", {"throttle": 0.25})
    assert ok and err is None
    assert holds[-1] == (VK_W, 0.25)


def test_scs_pad_factory_failure_falls_back_to_keyboard() -> None:
    holds: list[int] = []

    def boom() -> Any:
        raise RuntimeError("no vigem")

    def record(vk: int, *, hold_s: float) -> None:
        _ = hold_s
        holds.append(vk)

    driver = ScsDriver(pad_factory=boom, key_hold_fn=record)
    ok, err = driver.execute("scs.brake", {"fraction": 1.0})
    assert ok and err is None
    assert driver.mode == "keyboard"
    assert holds == [VK_S]


def test_scs_unknown_action() -> None:
    driver = ScsDriver(pad_factory=FakePad)
    ok, err = driver.execute("scs.honk", {})
    assert not ok
    assert err is not None and "unknown" in err


def test_factory_keyboard_prefers_keyboard_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TITAN_PLAY_BACKEND", "keyboard")
    monkeypatch.setenv("TITAN_GAME_SLUG", "ets2")
    settings = PlaySettings.from_environ()
    driver = build_driver(settings, session_id=UUID(int=47), data_dir=None)
    assert isinstance(driver, ScsDriver)
    holds: list[int] = []

    def record(vk: int, *, hold_s: float) -> None:
        _ = hold_s
        holds.append(vk)

    driver._key_hold_fn = record  # type: ignore[attr-defined]
    ok, err = driver.execute("scs.throttle", {"throttle": 0.2})
    assert ok and err is None
    assert driver.mode == "keyboard"
    assert holds == [VK_W]


def test_executor_with_fake_scs_pad(tmp_path: Path) -> None:
    pad = FakePad()
    driver = ScsDriver(pad_factory=lambda: pad)
    ex = PlayExecutor(session_id=UUID(int=4702), data_dir=tmp_path, driver=driver)
    ok, err, latency = ex.execute("scs.throttle", {"throttle": 0.6})
    assert ok and err is None and latency >= 0
    assert pad.right == [0.6]

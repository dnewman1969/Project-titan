"""kRPC driver (mocked connection)."""

from __future__ import annotations

from typing import Any

import pytest

from titan_actions.drivers import krpc_driver


class _Control:
    throttle: float = 0.0
    sas: bool = False
    rcs: bool = False
    brakes: bool = False
    staged: int = 0

    def activate_next_stage(self) -> None:
        self.staged += 1


class _Vessel:
    def __init__(self) -> None:
        self.control = _Control()


class _SpaceCenter:
    active_vessel = _Vessel()


class _Conn:
    space_center = _SpaceCenter()


@pytest.fixture(autouse=True)
def _reset_krpc_conn() -> None:
    krpc_driver._CONN = None
    krpc_driver._CONN_KEY = None


def test_krpc_throttle_and_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(krpc_driver, "_connect", lambda *_a, **_k: _Conn())
    from titan_actions.drivers.krpc_driver import KrpcDriver

    driver = KrpcDriver(host="127.0.0.1", rpc_port=50000, stream_port=50001)
    ok, err = driver.execute("ksp.throttle", {"throttle": 0.8})
    assert ok and err is None
    vessel = _Conn.space_center.active_vessel
    assert vessel.control.throttle == 0.8
    ok, err = driver.execute("ksp.stage", {})
    assert ok and vessel.control.staged == 1


def test_krpc_connect_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any, **_k: Any) -> Any:
        raise OSError("refused")

    monkeypatch.setattr(krpc_driver, "_connect", boom)
    from titan_actions.drivers.krpc_driver import KrpcDriver

    ok, err = KrpcDriver(host="127.0.0.1", rpc_port=1, stream_port=2).execute("ksp.throttle", {})
    assert not ok
    assert err is not None and "refused" in err

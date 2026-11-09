"""Play attach resolve + readiness probes."""

from __future__ import annotations

import errno

from titan_core.play_attach import (
    attach_probe_timeout_s,
    probe_attach,
    probe_hil,
    probe_krpc,
    probe_scs,
    resolve_backend,
    resolve_session_source,
)


def test_resolve_backend_and_source() -> None:
    assert resolve_backend("ksp", source="live") == "krpc"
    assert resolve_backend("ets2", source="live") == "scs"
    assert resolve_backend("ats", source="live") == "scs"
    assert resolve_backend("unknown", source="live") == "hil"
    assert resolve_backend("ksp", source="fixture") == "hil"
    assert resolve_session_source(session_source="live", demo_telemetry=False, has_install=True) == "live"
    assert resolve_session_source(session_source=None, demo_telemetry=True, has_install=True) == "fixture"
    assert resolve_session_source(session_source="live", demo_telemetry=False, has_install=False) == "fixture"


def test_probe_hil_and_fixture_attach() -> None:
    hil = probe_hil(source="fixture")
    assert hil.ready is True and hil.backend == "hil"
    assert "HIL" in hil.message or "hil" in hil.message.lower()
    attach = probe_attach(game_slug="ksp", source="fixture")
    assert attach.backend == "hil"
    assert attach.as_dict()["ready"] is True


def test_attach_probe_timeout_env(monkeypatch: object) -> None:
    monkeypatch.delenv("TITAN_PLAY_ATTACH_TIMEOUT_S", raising=False)  # type: ignore[attr-defined]
    assert attach_probe_timeout_s() == 0.6
    monkeypatch.setenv("TITAN_PLAY_ATTACH_TIMEOUT_S", "2.5")  # type: ignore[attr-defined]
    assert attach_probe_timeout_s() == 2.5
    monkeypatch.setenv("TITAN_PLAY_ATTACH_TIMEOUT_S", "not-a-number")  # type: ignore[attr-defined]
    assert attach_probe_timeout_s() == 0.6
    monkeypatch.setenv("TITAN_PLAY_ATTACH_TIMEOUT_S", "99")  # type: ignore[attr-defined]
    assert attach_probe_timeout_s() == 5.0


def test_probe_krpc_unreachable() -> None:
    # Port 1 is almost never listening; expect a soft not-ready result.
    attach = probe_krpc(host="127.0.0.1", rpc_port=1, stream_port=2, timeout_s=0.05)
    assert attach.backend == "krpc"
    assert attach.ready is False
    assert "kRPC" in attach.message


def test_probe_krpc_timeout_message(monkeypatch: object) -> None:
    import titan_core.play_attach as mod

    def timeout_connect(*_a: object, **_k: object) -> None:
        exc = OSError()
        exc.errno = errno.ETIMEDOUT
        raise exc

    monkeypatch.setattr(mod.socket, "create_connection", timeout_connect)  # type: ignore[attr-defined]
    attach = probe_krpc(host="127.0.0.1", rpc_port=50000, stream_port=50001, timeout_s=0.05)
    assert attach.ready is False
    assert "Timed out" in attach.message


def test_probe_krpc_open_port(monkeypatch: object) -> None:
    class _Sock:
        def __enter__(self) -> _Sock:
            return self

        def __exit__(self, *_a: object) -> None:
            return None

    def fake_connect(address: object, **_k: object) -> _Sock:
        _host, port = address
        assert port in {50000, 50001}
        return _Sock()

    import titan_core.play_attach as mod

    monkeypatch.setattr(mod.socket, "create_connection", fake_connect)  # type: ignore[attr-defined]
    attach = probe_krpc(host="127.0.0.1", rpc_port=50000, stream_port=50001)
    assert attach.ready is True
    assert attach.backend == "krpc"
    assert attach.detail.get("stream_reachable") is True


def test_probe_krpc_rpc_open_stream_closed(monkeypatch: object) -> None:
    class _Sock:
        def __enter__(self) -> _Sock:
            return self

        def __exit__(self, *_a: object) -> None:
            return None

    def fake_connect(address: object, **_k: object) -> _Sock:
        _host, port = address
        if port == 50000:
            return _Sock()
        raise ConnectionRefusedError

    import titan_core.play_attach as mod

    monkeypatch.setattr(mod.socket, "create_connection", fake_connect)  # type: ignore[attr-defined]
    attach = probe_krpc(host="127.0.0.1", rpc_port=50000, stream_port=50001)
    assert attach.ready is False
    assert "stream" in attach.message.lower()


def test_probe_scs_and_keyboard_backend(monkeypatch: object) -> None:
    import titan_core.play_attach as mod

    monkeypatch.setattr(mod.sys, "platform", "linux")  # type: ignore[attr-defined]
    linux = probe_scs()
    assert linux.ready is False
    assert linux.backend == "scs"

    monkeypatch.setattr(mod.sys, "platform", "win32")  # type: ignore[attr-defined]
    monkeypatch.setattr(mod, "_scs_telemetry_shm_open", lambda: True)
    win = probe_scs()
    assert win.ready is True
    assert "telemetry" in win.message.lower()

    monkeypatch.setattr(mod, "_scs_telemetry_shm_open", lambda: False)
    waiting = probe_scs()
    assert waiting.ready is False
    assert "SCSTelemetry" in waiting.message or "scs-telemetry" in waiting.message

    # resolve_backend never returns keyboard; exercise probe_attach remap after monkeypatch.
    monkeypatch.setattr(mod.sys, "platform", "linux")  # type: ignore[attr-defined]
    monkeypatch.setattr(mod, "resolve_backend", lambda *_a, **_k: "keyboard")
    kb = probe_attach(game_slug="ets2", source="live")
    assert kb.backend == "keyboard"
    assert kb.ready is False
    assert "scs" in kb.message.lower() or "windows" in kb.message.lower()


def test_probe_attach_live_krpc_and_env_ports(monkeypatch: object) -> None:
    import titan_core.play_attach as mod

    calls: list[tuple[str, int, int]] = []

    def fake_probe_krpc(**kwargs: object) -> object:
        calls.append((str(kwargs["host"]), int(kwargs["rpc_port"]), int(kwargs["stream_port"])))  # type: ignore[index]
        return probe_hil(source="live")

    monkeypatch.setattr(mod, "probe_krpc", fake_probe_krpc)
    monkeypatch.setenv("TITAN_KRPC_HOST", "10.0.0.2")  # type: ignore[attr-defined]
    monkeypatch.setenv("TITAN_KRPC_RPC_PORT", "60000")  # type: ignore[attr-defined]
    monkeypatch.setenv("TITAN_KRPC_STREAM_PORT", "60001")  # type: ignore[attr-defined]
    attach = probe_attach(game_slug="ksp", source="live")
    assert attach.backend == "hil"
    assert calls == [("10.0.0.2", 60000, 60001)]


def test_scs_telemetry_shm_mmap_success(monkeypatch: object) -> None:
    import titan_core.play_attach as mod

    closed = {"ok": False}

    class _Map:
        def close(self) -> None:
            closed["ok"] = True

    monkeypatch.setattr(mod.os, "name", "nt")
    monkeypatch.setattr(mod.mmap, "mmap", lambda *_a, **_k: _Map())  # type: ignore[attr-defined]
    assert mod._scs_telemetry_shm_open() is True
    assert closed["ok"] is True

"""Play attach resolve + readiness probes."""

from __future__ import annotations

from titan_core.play_attach import (
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


def test_probe_krpc_unreachable() -> None:
    # Port 1 is almost never listening; expect a soft not-ready result.
    attach = probe_krpc(host="127.0.0.1", rpc_port=1, stream_port=2, timeout_s=0.05)
    assert attach.backend == "krpc"
    assert attach.ready is False
    assert "kRPC" in attach.message


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

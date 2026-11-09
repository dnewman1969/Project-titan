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

    def fake_connect(*_a: object, **_k: object) -> _Sock:
        return _Sock()

    import titan_core.play_attach as mod

    monkeypatch.setattr(mod.socket, "create_connection", fake_connect)  # type: ignore[attr-defined]
    attach = probe_krpc(host="127.0.0.1", rpc_port=50000, stream_port=50001)
    assert attach.ready is True
    assert attach.backend == "krpc"


def test_probe_scs_and_keyboard_backend(monkeypatch: object) -> None:
    import titan_core.play_attach as mod

    monkeypatch.setattr(mod.sys, "platform", "linux")  # type: ignore[attr-defined]
    linux = probe_scs()
    assert linux.ready is False
    assert linux.backend == "scs"

    monkeypatch.setattr(mod.sys, "platform", "win32")  # type: ignore[attr-defined]
    win = probe_scs()
    assert win.ready is True
    assert "Windows" in win.message

    # Force keyboard backend branch via resolve_backend override path in probe_attach.
    # resolve_backend never returns keyboard; exercise via probe_attach after monkeypatch.
    monkeypatch.setattr(mod, "resolve_backend", lambda *_a, **_k: "keyboard")
    kb = probe_attach(game_slug="ets2", source="live")
    assert kb.backend == "keyboard"
    assert kb.ready is True

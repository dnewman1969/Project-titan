"""Play attach resolution and readiness probes."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from titan_actions.attach import (
    probe_attach,
    probe_hil,
    resolve_backend,
    resolve_session_source,
)
from titan_actions.executor import PlayExecutor
from titan_actions.play_env import PlaySettings


def test_resolve_backend_live_and_fixture() -> None:
    assert resolve_backend("ksp", source="live") == "krpc"
    assert resolve_backend("ets2", source="live") == "scs"
    assert resolve_backend("ats", source="live") == "scs"
    assert resolve_backend("ksp", source="fixture") == "hil"


def test_resolve_session_source() -> None:
    assert resolve_session_source(session_source="live", demo_telemetry=False, has_install=True) == "live"
    assert resolve_session_source(session_source="live", demo_telemetry=False, has_install=False) == "fixture"
    assert (
        resolve_session_source(session_source="fixture", demo_telemetry=False, has_install=True) == "fixture"
    )
    assert resolve_session_source(session_source=None, demo_telemetry=True, has_install=True) == "fixture"


def test_probe_hil_always_ready() -> None:
    attach = probe_hil()
    assert attach.ready is True
    assert attach.backend == "hil"


def test_probe_attach_fixture_uses_hil() -> None:
    attach = probe_attach(game_slug="ksp", source="fixture")
    assert attach.backend == "hil"
    assert attach.ready is True
    assert "HIL" in attach.message or "hil" in attach.message.lower()


def test_executor_writes_attach_json(tmp_path: Path) -> None:
    settings = PlaySettings(
        backend="hil",
        game_slug="ksp",
        krpc_host="127.0.0.1",
        krpc_rpc_port=50000,
        krpc_stream_port=50001,
        hil_trace=False,
    )
    executor = PlayExecutor(session_id=uuid4(), data_dir=tmp_path, settings=settings)
    path = tmp_path / "play_attach.json"
    assert path.is_file()
    assert executor.attach.backend == "hil"
    text = path.read_text(encoding="utf-8")
    assert '"backend": "hil"' in text

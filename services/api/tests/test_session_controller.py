"""SessionController process spawning."""

from __future__ import annotations

from uuid import UUID

from titan_api.session_controller import SessionController


def test_start_actions_tracks_child() -> None:
    launched: list[list[str]] = []

    class _Proc:
        def terminate(self) -> None:
            pass

        def wait(self, timeout: float = 0) -> int:
            return 0

    env_captured: dict[str, object] = {}

    def fake_spawn_env(cmd: list[str], **_kwargs: object) -> _Proc:
        launched.append(cmd)
        env_captured["env"] = _kwargs.get("env")
        return _Proc()

    ctl = SessionController(spawn=fake_spawn_env)
    sid = UUID(int=9)
    data_root = "C:/Titan/sessions/unit-test"
    ctl.start_actions(sid, game_slug="ksp", data_dir=data_root, play_backend="hil")
    assert launched
    assert "-m" in launched[0] and "titan_actions" in launched[0]
    assert "--game-slug" in launched[0]
    env = env_captured.get("env")
    assert isinstance(env, dict)
    assert env.get("TITAN_SESSION_DATA_DIR") == data_root
    assert env.get("TITAN_PLAY_BACKEND") == "hil"
    ctl.stop_actions(sid)


def test_start_orchestrator_passes_play_env() -> None:
    captured: dict[str, object] = {}

    class _Proc:
        def terminate(self) -> None:
            pass

        def wait(self, timeout: float = 0) -> int:
            return 0

    def fake_spawn(cmd: list[str], **kwargs: object) -> _Proc:
        captured["env"] = kwargs.get("env")
        return _Proc()

    ctl = SessionController(spawn=fake_spawn)
    sid = UUID(int=10)
    data_root = "C:/Titan/sessions/unit-test"
    ctl.start_orchestrator(sid, play_enabled=True, data_dir=data_root)
    env = captured.get("env")
    assert isinstance(env, dict)
    assert env.get("TITAN_SESSION_PLAY") == "1"
    assert env.get("TITAN_SESSION_DATA_DIR") == data_root


def test_start_orchestrator_idempotent_and_is_running() -> None:
    class _Proc:
        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            pass

        def wait(self, timeout: float = 0) -> int:
            return 0

    ctl = SessionController(spawn=lambda *_a, **_k: _Proc())
    sid = UUID(int=11)
    first = ctl.start_orchestrator(sid, game_slug="ksp")
    second = ctl.start_orchestrator(sid, game_slug="ksp")
    assert first is second
    assert ctl.is_running(sid)
    ctl.stop_orchestrator(sid)
    assert not ctl.is_running(sid)

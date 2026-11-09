"""Session state machine and orchestrator process launcher (M6.T6)."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import UUID


@dataclass
class OrchestratorProcess:
    session_id: UUID
    popen: subprocess.Popen[bytes]
    game_slug: str


@dataclass
class ActionsProcess:
    session_id: UUID
    popen: subprocess.Popen[bytes]


@dataclass
class SessionController:
    """Starts and stops `titan-orchestrator` children for live sessions."""

    spawn: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen
    _children: dict[UUID, OrchestratorProcess] = field(default_factory=dict)
    _actions: dict[UUID, ActionsProcess] = field(default_factory=dict)

    def start_orchestrator(
        self,
        session_id: UUID,
        *,
        game_slug: str = "ksp",
        play_enabled: bool = False,
        data_dir: str | None = None,
    ) -> OrchestratorProcess:
        if session_id in self._children:
            return self._children[session_id]
        cmd = [
            sys.executable,
            "-m",
            "titan_orchestrator",
            "--session-id",
            str(session_id),
            "--game-slug",
            game_slug,
        ]
        extra: dict[str, str] = {}
        if play_enabled:
            extra["TITAN_SESSION_PLAY"] = "1"
        if data_dir:
            extra["TITAN_SESSION_DATA_DIR"] = data_dir
        env = {**os.environ, **extra} if extra else None
        proc = self.spawn(cmd, env=env) if env is not None else self.spawn(cmd)
        child = OrchestratorProcess(session_id=session_id, popen=proc, game_slug=game_slug)
        self._children[session_id] = child
        return child

    def start_actions(
        self,
        session_id: UUID,
        *,
        game_slug: str = "ksp",
        data_dir: str | None = None,
        play_backend: str | None = None,
    ) -> ActionsProcess:
        if session_id in self._actions:
            return self._actions[session_id]
        cmd = [
            sys.executable,
            "-m",
            "titan_actions",
            "--session-id",
            str(session_id),
            "--game-slug",
            game_slug,
        ]
        env = {**os.environ, "TITAN_GAME_SLUG": game_slug}
        if data_dir:
            env["TITAN_SESSION_DATA_DIR"] = data_dir
        # Explicit backend: hil for fixture, krpc/scs when an install is attached.
        if play_backend:
            env["TITAN_PLAY_BACKEND"] = play_backend
        proc = self.spawn(cmd, env=env)
        child = ActionsProcess(session_id=session_id, popen=proc)
        self._actions[session_id] = child
        return child

    def stop_orchestrator(self, session_id: UUID) -> None:
        child = self._children.pop(session_id, None)
        if child is None:
            return
        child.popen.terminate()
        try:
            child.popen.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.popen.kill()

    def stop_actions(self, session_id: UUID) -> None:
        child = self._actions.pop(session_id, None)
        if child is None:
            return
        child.popen.terminate()
        try:
            child.popen.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.popen.kill()

    def restart_orchestrator(
        self,
        session_id: UUID,
        *,
        game_slug: str = "ksp",
        play_enabled: bool = False,
        data_dir: str | None = None,
    ) -> OrchestratorProcess:
        self.stop_orchestrator(session_id)
        return self.start_orchestrator(
            session_id,
            game_slug=game_slug,
            play_enabled=play_enabled,
            data_dir=data_dir,
        )

    def is_running(self, session_id: UUID) -> bool:
        child = self._children.get(session_id)
        return child is not None and child.popen.poll() is None

    def actions_running(self, session_id: UUID) -> bool:
        child = self._actions.get(session_id)
        return child is not None and child.popen.poll() is None

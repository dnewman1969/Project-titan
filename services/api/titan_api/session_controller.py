"""Session state machine and orchestrator process launcher (M6.T6)."""

from __future__ import annotations

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
class SessionController:
    """Starts and stops `titan-orchestrator` children for live sessions."""

    spawn: Callable[[list[str]], subprocess.Popen[bytes]] = subprocess.Popen
    _children: dict[UUID, OrchestratorProcess] = field(default_factory=dict)

    def start_orchestrator(self, session_id: UUID, *, game_slug: str = "ksp") -> OrchestratorProcess:
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
        proc = self.spawn(cmd)
        child = OrchestratorProcess(session_id=session_id, popen=proc, game_slug=game_slug)
        self._children[session_id] = child
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

    def is_running(self, session_id: UUID) -> bool:
        child = self._children.get(session_id)
        return child is not None and child.popen.poll() is None

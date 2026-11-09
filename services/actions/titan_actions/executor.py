"""Execute approved play actions (beta: logs + optional kRPC throttle stub)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from titan_core.logging import get_logger

log = get_logger(__name__)


class PlayExecutor:
    def __init__(self, *, session_id: UUID, data_dir: Path | None = None) -> None:
        self.session_id = session_id
        self._log = data_dir / "play.ndjson" if data_dir is not None else None

    def execute(self, action_id: str, params: dict[str, Any]) -> tuple[bool, str | None]:
        try:
            self._record(action_id, params)
            if action_id == "ksp.throttle":
                throttle = float(params.get("throttle", 0.5))
                log.info("ksp_throttle", session_id=str(self.session_id), throttle=throttle)
                return True, None
            if action_id == "scs.brake":
                log.info("scs_brake", session_id=str(self.session_id), params=params)
                return True, None
            return False, f"unknown action {action_id!r}"
        except (TypeError, ValueError) as exc:
            return False, str(exc)

    def _record(self, action_id: str, params: dict[str, Any]) -> None:
        if self._log is None:
            return
        self._log.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"action_id": action_id, "params": params}, separators=(",", ":")) + "\n"
        with self._log.open("a", encoding="utf-8") as fh:
            fh.write(line)

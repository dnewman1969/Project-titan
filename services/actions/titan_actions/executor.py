"""Execute approved play actions via game drivers (kRPC, SCS, or HIL)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from titan_actions.drivers.factory import build_driver
from titan_actions.drivers.protocol import PlayDriver
from titan_actions.play_env import PlaySettings
from titan_core.logging import get_logger

log = get_logger(__name__)


class PlayExecutor:
    def __init__(
        self,
        *,
        session_id: UUID,
        data_dir: Path | None = None,
        driver: PlayDriver | None = None,
        settings: PlaySettings | None = None,
    ) -> None:
        self.session_id = session_id
        self._log = data_dir / "play.ndjson" if data_dir is not None else None
        cfg = settings or PlaySettings.from_environ()
        self._driver = driver or build_driver(cfg, session_id=session_id, data_dir=data_dir)

    def execute(self, action_id: str, params: dict[str, Any]) -> tuple[bool, str | None]:
        try:
            self._record(action_id, params)
            ok, err = self._driver.execute(action_id, params)
            if not ok:
                log.warning("play_failed", action_id=action_id, err=err, session_id=str(self.session_id))
            return ok, err
        except (TypeError, ValueError) as exc:
            return False, str(exc)

    def _record(self, action_id: str, params: dict[str, Any]) -> None:
        if self._log is None:
            return
        self._log.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({"action_id": action_id, "params": params}, separators=(",", ":")) + "\n"
        with self._log.open("a", encoding="utf-8") as fh:
            fh.write(line)

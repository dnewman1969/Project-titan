"""Execute approved play actions via game drivers (kRPC, SCS, or HIL)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from titan_actions.attach import PlayAttach, probe_attach
from titan_actions.drivers.factory import build_driver
from titan_actions.drivers.protocol import PlayDriver
from titan_actions.play_env import PlaySettings
from titan_core.clock import utc_now
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
        attach: PlayAttach | None = None,
    ) -> None:
        self.session_id = session_id
        self._data_dir = data_dir
        self._log = data_dir / "play.ndjson" if data_dir is not None else None
        cfg = settings or PlaySettings.from_environ()
        self._settings = cfg
        source: Literal["live", "fixture"] = "fixture" if cfg.backend == "hil" else "live"
        self.attach = attach or probe_attach(game_slug=cfg.game_slug, source=source, settings=cfg)
        self._driver = driver or build_driver(cfg, session_id=session_id, data_dir=data_dir)
        self._write_attach()

    def _write_attach(self) -> None:
        if self._data_dir is None:
            return
        self._data_dir.mkdir(parents=True, exist_ok=True)
        path = self._data_dir / "play_attach.json"
        path.write_text(json.dumps(self.attach.as_dict(), indent=2) + "\n", encoding="utf-8")
        log.info(
            "play_attach",
            session_id=str(self.session_id),
            backend=self.attach.backend,
            ready=self.attach.ready,
            source=self.attach.source,
            message=self.attach.message,
        )

    def execute(self, action_id: str, params: dict[str, Any]) -> tuple[bool, str | None, int]:
        """Run one action. Returns (ok, error, latency_ms)."""
        started = time.perf_counter()
        try:
            ok, err = self._driver.execute(action_id, params)
            latency_ms = max(0, int((time.perf_counter() - started) * 1000))
            self._record(action_id, params, ok=ok, err=err, latency_ms=latency_ms)
            if not ok:
                log.warning(
                    "play_failed",
                    action_id=action_id,
                    err=err,
                    session_id=str(self.session_id),
                    latency_ms=latency_ms,
                )
            else:
                log.info(
                    "play_ok",
                    action_id=action_id,
                    session_id=str(self.session_id),
                    latency_ms=latency_ms,
                )
            return ok, err, latency_ms
        except Exception as exc:
            latency_ms = max(0, int((time.perf_counter() - started) * 1000))
            err = str(exc)
            self._record(action_id, params, ok=False, err=err, latency_ms=latency_ms)
            log.warning(
                "play_exception",
                action_id=action_id,
                err=err,
                session_id=str(self.session_id),
            )
            return False, err, latency_ms

    def _record(
        self,
        action_id: str,
        params: dict[str, Any],
        *,
        ok: bool,
        err: str | None,
        latency_ms: int,
    ) -> None:
        if self._log is None:
            return
        self._log.parent.mkdir(parents=True, exist_ok=True)
        line = (
            json.dumps(
                {
                    "t": utc_now().isoformat(),
                    "action_id": action_id,
                    "params": params,
                    "ok": ok,
                    "error": err,
                    "latency_ms": latency_ms,
                },
                separators=(",", ":"),
            )
            + "\n"
        )
        with self._log.open("a", encoding="utf-8") as fh:
            fh.write(line)

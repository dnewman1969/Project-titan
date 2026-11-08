"""Client for the supervisor's internal API on `127.0.0.1:8769` (Section 2.3)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from titan_core.config import SupervisorConfig
from titan_core.http import HTTPError, local_client
from titan_core.logging import get_logger
from titan_core.protocol.system import SupervisorStatus

log = get_logger(__name__)

SupervisorProbe = Callable[[], Awaitable[SupervisorStatus | None]]


def supervisor_probe(cfg: SupervisorConfig, token: str, *, timeout_s: float = 1.0) -> SupervisorProbe:
    """A coroutine function returning the supervisor's status, or None when it is not running."""

    async def probe() -> SupervisorStatus | None:
        try:
            async with local_client(timeout_s=timeout_s, token=token) as client:
                response = await client.get(f"{cfg.url}/status")
        except HTTPError:
            return None
        if response.status_code != 200:
            log.warning("supervisor_status_failed", status=response.status_code)
            return None
        return SupervisorStatus.model_validate_json(response.content)

    return probe

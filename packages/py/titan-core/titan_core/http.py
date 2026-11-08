"""The only place that may create HTTP clients (Section 9.7, enforced by lint-imports).

`local_client()` talks to Titan's own loopback services and to user-installed local servers
(Ollama, OBS). It never reads proxy settings from the environment and refuses any other host.
Internet egress (model pulls, research) gets its own allowlisted factory in the phase that needs it.
"""

from __future__ import annotations

import logging

import httpx

# httpx logs every request at INFO; health checks would flood the logs.
logging.getLogger("httpx").setLevel(logging.WARNING)

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})


class EgressBlocked(RuntimeError):
    """A request tried to leave the machine through the loopback-only client."""


async def _loopback_only(request: httpx.Request) -> None:
    if request.url.host not in LOOPBACK_HOSTS:
        raise EgressBlocked(f"{request.url.host} is not a loopback host")


def local_client(*, timeout_s: float = 2.0, token: str | None = None) -> httpx.AsyncClient:
    """An async client limited to loopback hosts, optionally sending `Authorization: Bearer`."""
    headers = {"Authorization": f"Bearer {token}"} if token else None
    return httpx.AsyncClient(
        timeout=timeout_s,
        trust_env=False,
        headers=headers,
        event_hooks={"request": [_loopback_only]},
    )


HTTPError = httpx.HTTPError
"""Base class of every transport and protocol error raised by these clients."""

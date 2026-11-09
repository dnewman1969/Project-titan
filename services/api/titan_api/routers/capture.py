"""Capture / OBS probe routes for Ops Center (live obs-websocket v5 status)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from titan_api.auth import Authenticated
from titan_core.health import check_obs
from titan_core.obs_ws import make_obs_client

router = APIRouter(prefix="/capture", tags=["capture"], dependencies=[Authenticated])


@router.get("/obs")
async def obs_capture_status() -> dict[str, Any]:
    """Reachability + websocket handshake for the Webcam / REC panels."""
    client = make_obs_client()
    tcp = await check_obs(client.host, client.port, timeout_s=min(0.8, client.timeout_s))
    payload: dict[str, Any] = {
        "state": tcp.state,
        "detail": tcp.detail,
        "host": client.host,
        "port": client.port,
        "connected": False,
        "version": None,
        "provision": None,
    }
    if tcp.state != "up":
        return payload
    try:
        await client.connect()
        try:
            version = await client.get_version()
            payload["connected"] = True
            payload["version"] = version
            payload["provision"] = await client.provision_titan_profile()
            status = await client.get_record_status()
            payload["record"] = {
                "active": status.active,
                "paused": status.paused,
                "duration_ms": status.duration_ms,
            }
        finally:
            await client.close()
    except (OSError, RuntimeError) as exc:
        payload["state"] = "degraded"
        payload["detail"] = str(exc)
        payload["connected"] = False
    return payload

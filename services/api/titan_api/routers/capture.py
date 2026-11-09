"""Capture / OBS probe routes for Ops Center (M8 beta stubs)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from titan_api.auth import Authenticated
from titan_core.health import check_obs
from titan_core.obs_ws import ObsClient

router = APIRouter(prefix="/capture", tags=["capture"], dependencies=[Authenticated])


@router.get("/obs")
async def obs_capture_status() -> dict[str, Any]:
    """Reachability + optional websocket handshake for the Webcam / REC panels."""
    tcp = await check_obs(timeout_s=0.8)
    payload: dict[str, Any] = {
        "state": tcp.state,
        "detail": tcp.detail,
        "host": ObsClient().host,
        "port": ObsClient().port,
        "connected": False,
        "version": None,
        "provision": None,
    }
    if tcp.state != "up":
        return payload
    client = ObsClient()
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

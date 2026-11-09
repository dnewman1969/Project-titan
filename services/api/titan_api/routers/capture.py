"""Capture / OBS probe routes for Ops Center (live obs-websocket v5 status)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from titan_api.auth import Authenticated
from titan_core.obs_ws import ObsConnectionError, make_obs_client, obs_connection_failure

router = APIRouter(prefix="/capture", tags=["capture"], dependencies=[Authenticated])


def _failure_payload(client_host: str, client_port: int, exc: BaseException) -> dict[str, Any]:
    if isinstance(exc, ObsConnectionError):
        state = "down" if exc.not_running else "degraded"
        detail = exc.detail
    else:
        state, detail = obs_connection_failure(exc)
    return {
        "state": state,
        "detail": detail,
        "host": client_host,
        "port": client_port,
        "connected": False,
        "version": None,
        "provision": None,
        "webcam": {"selected": False, "detail": detail},
    }


@router.get("/obs")
async def obs_capture_status() -> dict[str, Any]:
    """obs-websocket v5 handshake. HTTP 200 with connected=false is not a live session."""
    client = make_obs_client()
    payload: dict[str, Any] = {
        "state": "down",
        "detail": "OBS not running",
        "host": client.host,
        "port": client.port,
        "connected": False,
        "version": None,
        "provision": None,
        "webcam": {"selected": False, "detail": "OBS not running"},
    }
    try:
        await client.connect()
    except (OSError, RuntimeError) as exc:
        await client.close()
        return _failure_payload(client.host, client.port, exc)
    try:
        version = await client.get_version()
        payload["connected"] = True
        payload["state"] = "up"
        payload["detail"] = None
        payload["version"] = version
        payload["provision"] = await client.provision_titan_profile()
        status = await client.get_record_status()
        payload["record"] = {
            "active": status.active,
            "paused": status.paused,
            "duration_ms": status.duration_ms,
        }
        try:
            payload["webcam"] = await client.select_webcam_source()
        except (OSError, RuntimeError) as exc:
            payload["webcam"] = {"selected": False, "detail": str(exc)}
    except (OSError, RuntimeError) as exc:
        failed = _failure_payload(client.host, client.port, exc)
        # A socket that accepted the handshake and then failed is degraded, not "not running",
        # unless the peer actually went away.
        if failed["state"] == "down" and payload["connected"]:
            failed["state"] = "degraded"
            if failed["detail"] == "OBS not running":
                failed["detail"] = str(exc) or "OBS websocket closed"
                failed["webcam"] = {"selected": False, "detail": failed["detail"]}
        payload = failed
    finally:
        await client.close()
    return payload

"""Shared session recording start (API routes + session lifecycle)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_core.clock import utc_now
from titan_core.errors import ErrorCode, TitanError
from titan_core.ids import uuid7
from titan_core.obs_ws import ObsConnectionError, make_obs_client, obs_connection_failure
from titan_core.recording_manifest import (
    append_timeline_event,
    build_manifest,
    build_track_entries,
    default_preset,
    read_manifest,
    write_manifest,
)
from titan_db.models.recording import Recording
from titan_db.models.sessions import Session


def _dependency_detail(exc: BaseException) -> str:
    if isinstance(exc, ObsConnectionError):
        return exc.detail
    return obs_connection_failure(exc)[1]


def recording_json(row: Recording) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": row.id,
        "session_id": row.session_id,
        "state": row.state,
        "preset": row.preset,
        "start_mono_ns": row.start_mono_ns,
        "started_at": row.started_at,
        "stopped_at": row.stopped_at,
        "duration_ms": row.duration_ms,
        "root_dir": row.root_dir,
        "manifest_path": row.manifest_path,
        "error": row.error,
        "tracks": [],
        "obs": {"connected": False, "status": {}},
    }
    if row.manifest_path:
        manifest = read_manifest(Path(row.manifest_path))
        if manifest is not None:
            tracks = manifest.get("tracks")
            if isinstance(tracks, list):
                payload["tracks"] = tracks
            obs = manifest.get("obs")
            if isinstance(obs, dict):
                payload["obs"] = obs
    return payload


async def start_session_recording(db: AsyncSession, session_row: Session) -> dict[str, Any]:
    if session_row.state not in {"live", "paused", "starting"}:
        raise TitanError(
            ErrorCode.INVALID_STATE_TRANSITION,
            f"start recording requires a live session (state={session_row.state!r})",
        )
    existing = await db.scalar(
        select(Recording)
        .where(Recording.session_id == session_row.id)
        .where(Recording.state.in_(("starting", "recording")))
    )
    if existing is not None:
        return recording_json(existing)
    root = Path(session_row.data_dir) / "recording"
    await asyncio.to_thread(root.mkdir, parents=True, exist_ok=True)
    preset = default_preset()
    rec_id = uuid7()
    manifest_path = root / "manifest.json"
    client = make_obs_client()
    try:
        await client.connect()
    except (OSError, RuntimeError) as exc:
        await client.close()
        raise TitanError(ErrorCode.DEPENDENCY_UNAVAILABLE, _dependency_detail(exc), dependency="obs") from exc
    try:
        try:
            webcam = await client.select_webcam_source()
        except (OSError, RuntimeError) as exc:
            webcam = {"selected": False, "detail": str(exc)}
        provision = await client.provision_titan_profile()
        await client.start_recording(directory=str(root))
        status = await client.get_record_status()
    except (OSError, RuntimeError) as exc:
        raise TitanError(ErrorCode.DEPENDENCY_UNAVAILABLE, _dependency_detail(exc), dependency="obs") from exc
    finally:
        await client.close()

    obs_status: dict[str, Any] = {
        "active": True,
        "paused": status.paused,
        "duration_ms": status.duration_ms,
        "provision": provision,
        "webcam": webcam,
    }
    tracks = build_track_entries(obs_connected=True, root_dir=root)
    manifest = build_manifest(
        session_id=str(session_row.id),
        recording_id=str(rec_id),
        obs_active=True,
        obs_status=obs_status,
        preset=preset,
        tracks=tracks,
    )
    manifest["obs"]["provision"] = provision
    await asyncio.to_thread(write_manifest, manifest_path, manifest)
    await asyncio.to_thread(
        append_timeline_event,
        root,
        {
            "t": utc_now().isoformat(),
            "kind": "recording.start",
            "message": "OBS StartRecord",
            "recording_id": str(rec_id),
            "obs": obs_status,
            "tracks": len(tracks),
        },
    )
    row = Recording(
        id=rec_id,
        session_id=session_row.id,
        state="recording",
        preset=preset,
        start_mono_ns=session_row.clock_origin_mono_ns,
        started_at=utc_now(),
        root_dir=str(root),
        manifest_path=str(manifest_path),
        error=None,
    )
    db.add(row)
    await db.flush()
    return recording_json(row)

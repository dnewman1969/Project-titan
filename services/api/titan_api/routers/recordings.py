"""Session recording control (M8.T1-T3 MVP)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_api.auth import Authenticated
from titan_api.deps import db_session
from titan_core.clock import utc_now
from titan_core.errors import ErrorCode, TitanError
from titan_core.ids import uuid7
from titan_core.obs_ws import ObsClient
from titan_core.recording_manifest import (
    append_timeline_event,
    build_manifest,
    default_preset,
    write_manifest,
)
from titan_db.models.recording import Recording
from titan_db.models.sessions import Session

router = APIRouter(tags=["recordings"], dependencies=[Authenticated])
SessionDep = Depends(db_session)


def _recording_json(row: Recording) -> dict[str, Any]:
    return {
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
    }


async def _session_or_404(db: AsyncSession, session_id: UUID) -> Session:
    row = await db.scalar(select(Session).where(Session.id == session_id))
    if row is None:
        raise TitanError(ErrorCode.NOT_FOUND, f"session {session_id} not found")
    return row


@router.get("/sessions/{session_id}/recordings/active")
async def active_recording(session_id: UUID, db: AsyncSession = SessionDep) -> dict[str, Any]:
    await _session_or_404(db, session_id)
    row = await db.scalar(
        select(Recording)
        .where(Recording.session_id == session_id)
        .where(Recording.state.in_(("starting", "recording", "stopping")))
        .order_by(Recording.created_at.desc())
        .limit(1)
    )
    if row is None:
        return {"item": None}
    return {"item": _recording_json(row)}


@router.post("/sessions/{session_id}/recordings/start", status_code=status.HTTP_201_CREATED)
async def start_recording(session_id: UUID, db: AsyncSession = SessionDep) -> dict[str, Any]:
    session_row = await _session_or_404(db, session_id)
    if session_row.state not in {"live", "paused", "starting"}:
        raise TitanError(
            ErrorCode.INVALID_STATE_TRANSITION,
            f"start recording requires a live session (state={session_row.state!r})",
        )
    existing = await db.scalar(
        select(Recording)
        .where(Recording.session_id == session_id)
        .where(Recording.state.in_(("starting", "recording")))
    )
    if existing is not None:
        raise TitanError(ErrorCode.CONFLICT, "recording already active")
    root = Path(session_row.data_dir) / "recording"
    await asyncio.to_thread(root.mkdir, parents=True, exist_ok=True)
    preset = default_preset()
    rec_id = uuid7()
    manifest_path = root / "manifest.json"
    obs_status: dict[str, Any] = {}
    obs_error: str | None = None
    state = "recording"
    try:
        client = ObsClient()
        await client.connect()
        try:
            status = await client.get_record_status()
            obs_status = {"active": status.active, "paused": status.paused, "duration_ms": status.duration_ms}
            await client.start_recording()
        finally:
            await client.close()
    except (OSError, RuntimeError) as exc:
        obs_error = str(exc)
        state = "recording"
        obs_status = {"degraded": True, "message": obs_error}
    manifest = build_manifest(
        session_id=str(session_id),
        recording_id=str(rec_id),
        obs_active=obs_error is None,
        obs_status=obs_status,
        preset=preset,
    )
    await asyncio.to_thread(write_manifest, manifest_path, manifest)
    await asyncio.to_thread(
        append_timeline_event,
        root,
        {
            "t": utc_now().isoformat(),
            "kind": "recording.start",
            "recording_id": str(rec_id),
            "obs": obs_status,
        },
    )
    placeholder = root / "tracks" / "game-placeholder.txt"
    await asyncio.to_thread(
        _write_placeholder_track,
        placeholder,
        "Game video lands when OBS is connected; this session still records metadata and timeline.",
    )
    row = Recording(
        id=rec_id,
        session_id=session_id,
        state=state,
        preset=preset,
        start_mono_ns=session_row.clock_origin_mono_ns,
        started_at=utc_now(),
        root_dir=str(root),
        manifest_path=str(manifest_path),
        error=obs_error,
    )
    db.add(row)
    await db.flush()
    return _recording_json(row)


@router.post("/sessions/{session_id}/recordings/stop", status_code=status.HTTP_200_OK)
async def stop_recording(session_id: UUID, db: AsyncSession = SessionDep) -> dict[str, Any]:
    await _session_or_404(db, session_id)
    row = await db.scalar(
        select(Recording).where(Recording.session_id == session_id).where(Recording.state == "recording")
    )
    if row is None:
        raise TitanError(ErrorCode.NOT_FOUND, "no active recording")
    row.state = "stopping"
    obs_error: str | None = None
    try:
        client = ObsClient()
        await client.connect()
        try:
            await client.stop_recording()
        finally:
            await client.close()
    except (OSError, RuntimeError) as exc:
        obs_error = str(exc)
    row.state = "complete"
    row.stopped_at = utc_now()
    if row.started_at is not None and row.stopped_at is not None:
        delta = row.stopped_at - row.started_at
        row.duration_ms = int(delta.total_seconds() * 1000)
    if obs_error and row.error is None:
        row.error = obs_error
    if row.root_dir:
        await asyncio.to_thread(
            append_timeline_event,
            Path(row.root_dir),
            {
                "t": utc_now().isoformat(),
                "kind": "recording.stop",
                "recording_id": str(row.id),
                "duration_ms": row.duration_ms,
            },
        )
    await db.flush()
    return _recording_json(row)


def _write_placeholder_track(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(message + "\n", encoding="utf-8")

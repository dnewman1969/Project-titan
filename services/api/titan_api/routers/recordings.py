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
from titan_api.recording_ops import recording_json, start_session_recording
from titan_core.clock import utc_now
from titan_core.errors import ErrorCode, TitanError
from titan_core.obs_ws import ObsClient
from titan_core.recording_manifest import append_timeline_event, read_timeline_events
from titan_db.models.recording import Recording
from titan_db.models.sessions import Session

router = APIRouter(tags=["recordings"], dependencies=[Authenticated])
SessionDep = Depends(db_session)


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
    return {"item": recording_json(row)}


@router.get("/sessions/{session_id}/recordings/timeline")
async def recording_timeline(
    session_id: UUID,
    limit: int = 80,
    db: AsyncSession = SessionDep,
) -> dict[str, Any]:
    session_row = await _session_or_404(db, session_id)
    capped = max(1, min(limit, 500))
    root = Path(session_row.data_dir) / "recording"
    events = await asyncio.to_thread(read_timeline_events, root, limit=capped)
    active = await db.scalar(
        select(Recording)
        .where(Recording.session_id == session_id)
        .where(Recording.state.in_(("starting", "recording", "stopping")))
        .order_by(Recording.created_at.desc())
        .limit(1)
    )
    return {
        "session_id": str(session_id),
        "recording": recording_json(active) if active is not None else None,
        "root_dir": str(root),
        "events": events,
    }


@router.post("/sessions/{session_id}/recordings/start", status_code=status.HTTP_201_CREATED)
async def start_recording(session_id: UUID, db: AsyncSession = SessionDep) -> dict[str, Any]:
    """Start REC; idempotent when a recording is already active (double-click safe)."""
    session_row = await _session_or_404(db, session_id)
    return await start_session_recording(db, session_row)


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
    return recording_json(row)

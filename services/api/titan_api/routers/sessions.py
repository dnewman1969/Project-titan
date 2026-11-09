"""Session lifecycle routes (Section 5.2, M6.T6)."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_api.auth import Authenticated
from titan_api.demo_replay import start_demo_replay
from titan_api.deps import db_session
from titan_api.session_telemetry import (
    fixture_fallback_path,
    start_live_telemetry,
    stop_all_session_telemetry,
)
from titan_core.clock import SessionClock, utc_now
from titan_core.config import expand_path
from titan_core.errors import ErrorCode, TitanError
from titan_core.ids import uuid7
from titan_db.models.games import Game, GameProfile
from titan_db.models.sessions import Session
from titan_db.repositories.blackboard import BlackboardRepository

router = APIRouter(tags=["sessions"], dependencies=[Authenticated])
SessionDep = Depends(db_session)


class MissionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    objective: str
    success_criteria: list[dict[str, Any]] = Field(default_factory=list)
    failure_criteria: list[dict[str, Any]] = Field(default_factory=list)


class CreateSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game_id: UUID | None = None
    game_slug: str | None = None
    game_profile_id: UUID | None = None
    team_id: UUID | None = None
    title: str | None = None
    mode: str = "observe"
    settings: dict[str, Any] = Field(default_factory=dict)
    replay_of_session_id: UUID | None = None
    missions: list[MissionCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def _game_ref_present(self) -> CreateSession:
        if self.game_id is None and not self.game_slug:
            raise ValueError("game_id or game_slug is required")
        return self


class StartSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    launch_game: bool = False


class StopSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: str | None = None


def _session_json(row: Session) -> dict[str, Any]:
    return {
        "id": row.id,
        "game_id": row.game_id,
        "game_profile_id": row.game_profile_id,
        "team_id": row.team_id,
        "title": row.title,
        "mode": row.mode,
        "state": row.state,
        "started_at": row.started_at,
        "ended_at": row.ended_at,
        "outcome": row.outcome,
        "data_dir": row.data_dir,
        "settings": row.settings,
    }


async def _session_or_404(session: AsyncSession, session_id: UUID) -> Session:
    row = await session.scalar(select(Session).where(Session.id == session_id))
    if row is None:
        raise TitanError(ErrorCode.NOT_FOUND, f"session {session_id} not found")
    return row


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(body: CreateSession, db: AsyncSession = SessionDep) -> dict[str, Any]:
    if body.mode == "autonomous":
        raise TitanError(ErrorCode.NOT_IMPLEMENTED_IN_PHASE, "autonomous mode is Phase 4+")
    if body.game_id is not None:
        game = await db.scalar(select(Game).where(Game.id == body.game_id))
    else:
        game = await db.scalar(select(Game).where(Game.slug == body.game_slug))
    if game is None:
        raise TitanError(ErrorCode.NOT_FOUND, "game not found")
    resolved_game_id = game.id
    clock = SessionClock.start()
    data_dir = str(expand_path(f"%LOCALAPPDATA%/Titan/sessions/{uuid7()}"))
    await asyncio.to_thread(Path(data_dir).mkdir, parents=True, exist_ok=True)
    row = Session(
        id=uuid7(),
        game_id=resolved_game_id,
        game_profile_id=body.game_profile_id,
        team_id=body.team_id,
        title=body.title,
        mode=body.mode,
        state="created",
        replay_of_session_id=body.replay_of_session_id,
        data_dir=data_dir,
        settings=body.settings,
        clock_origin_mono_ns=clock.origin_mono_ns,
        clock_origin_wall=clock.origin_wall,
    )
    db.add(row)
    await db.flush()
    return _session_json(row)


@router.get("/sessions/{session_id}")
async def get_session(session_id: UUID, db: AsyncSession = SessionDep) -> dict[str, Any]:
    row = await _session_or_404(db, session_id)
    return _session_json(row)


@router.post("/sessions/{session_id}/start", status_code=status.HTTP_202_ACCEPTED)
async def start_session(
    session_id: UUID,
    body: StartSession,
    request: Request,
    db: AsyncSession = SessionDep,
) -> dict[str, Any]:
    row = await _session_or_404(db, session_id)
    if row.state in {"starting", "live", "paused", "stopping"}:
        raise TitanError(ErrorCode.SESSION_ALREADY_LIVE, "session already active")
    if row.state != "created":
        raise TitanError(ErrorCode.INVALID_STATE_TRANSITION, f"cannot start from state {row.state!r}")
    row.state = "starting"
    row.started_at = utc_now()
    if row.clock_origin_mono_ns is None:
        clock = SessionClock.start()
        row.clock_origin_mono_ns = clock.origin_mono_ns
        row.clock_origin_wall = clock.origin_wall
    game_row = await db.scalar(select(Game).where(Game.id == row.game_id))
    game_slug = game_row.slug if game_row is not None else "ksp"
    controller = request.app.state.session_controller
    play_enabled = bool(row.settings.get("play_enabled", False))
    if row.settings.get("agents_enabled", True):
        controller.start_orchestrator(session_id, game_slug=game_slug, play_enabled=play_enabled)
    if play_enabled:
        controller.start_actions(session_id)
    row.state = "live"
    await db.flush()
    profile: GameProfile | None = None
    if row.game_profile_id is not None:
        profile = await db.scalar(select(GameProfile).where(GameProfile.id == row.game_profile_id))
    if row.settings.get("demo_telemetry", False):
        await start_demo_replay(session_id)
        await _seed_director_demo_line(db, session_id)
    elif profile is not None:
        await start_live_telemetry(session_id, game_slug=game_slug, install_path=profile.install_path)
    else:
        default_profile = await db.scalar(
            select(GameProfile)
            .where(GameProfile.game_id == row.game_id, GameProfile.is_default.is_(True))
            .limit(1)
        )
        if default_profile is not None:
            await start_live_telemetry(
                session_id, game_slug=game_slug, install_path=default_profile.install_path
            )
        elif fixture_fallback_path(game_slug) is not None:
            await start_demo_replay(session_id)
            await _seed_director_demo_line(db, session_id)
    if body.launch_game and profile is not None:
        exe = profile.executable_path

        def _launch() -> None:
            if Path(exe).is_file():
                subprocess.Popen([exe])  # noqa: S603

        await asyncio.to_thread(_launch)
    return _session_json(row)


async def _seed_director_demo_line(db: AsyncSession, session_id: UUID) -> None:
    repo = BlackboardRepository(db)
    if await repo.latest_entry(session_id, "notes", "director.hello") is not None:
        return
    bb_version = await repo.next_bb_version(session_id)
    await repo.append(
        session_id=session_id,
        section="notes",
        key="director.hello",
        version=1,
        op="put",
        value={
            "text": "I see fixture telemetry. Try to keep up, human — I already optimized the burn.",
        },
        author="agent:wernher",
        confidence=1.0,
        evidence=[],
        bb_version=bb_version,
    )


@router.post("/sessions/{session_id}/stop", status_code=status.HTTP_202_ACCEPTED)
async def stop_session(
    session_id: UUID,
    body: StopSession,
    request: Request,
    db: AsyncSession = SessionDep,
) -> dict[str, Any]:
    row = await _session_or_404(db, session_id)
    if row.state in {"ended", "failed"}:
        raise TitanError(ErrorCode.INVALID_STATE_TRANSITION, "session already ended")
    row.state = "stopping"
    stop_all_session_telemetry(session_id)
    controller = request.app.state.session_controller
    controller.stop_actions(session_id)
    controller.stop_orchestrator(session_id)
    row.state = "ended"
    row.ended_at = utc_now()
    row.outcome = body.outcome
    await db.flush()
    return _session_json(row)


@router.get("/sessions/{session_id}/blackboard")
async def get_blackboard(
    session_id: UUID,
    db: AsyncSession = SessionDep,
    sections: Annotated[list[str] | None, Query()] = None,
    since_version: Annotated[int | None, Query(alias="since_version")] = None,
) -> dict[str, Any]:
    await _session_or_404(db, session_id)
    repo = BlackboardRepository(db)
    bb_version, entries = await repo.snapshot(session_id, sections=sections, since_bb_version=since_version)
    return {
        "bb_version": bb_version,
        "entries": [
            {
                "section": row.section,
                "key": row.key,
                "version": row.version,
                "op": row.op,
                "value": row.value,
                "author": row.author,
                "confidence": row.confidence,
                "evidence": row.evidence,
                "bb_version": row.bb_version,
                "created_at": row.created_at,
                "expires_at": row.expires_at,
            }
            for row in entries
        ],
    }

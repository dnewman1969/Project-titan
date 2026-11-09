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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from titan_api.auth import Authenticated
from titan_api.demo_replay import start_demo_replay
from titan_api.deps import db_session
from titan_api.game_launch import game_process_argv
from titan_api.memory_ops import seed_prior_memories_on_blackboard, write_learning_on_session_end
from titan_api.session_lifecycle import end_session_row, supersede_other_live_sessions
from titan_api.session_telemetry import (
    fixture_fallback_path,
    start_live_telemetry,
)
from titan_core.clock import SessionClock, utc_now
from titan_core.config import expand_path
from titan_core.errors import ErrorCode, TitanError
from titan_core.ids import uuid7
from titan_core.play_attach import probe_attach, resolve_session_source, wait_probe_attach
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
    # Atomic create+start avoids the FastAPI yield-dep race where create commits AFTER
    # the HTTP response, so a follow-up /start can 404 on Windows (David HIL).
    auto_start: bool = False
    launch_game: bool = False

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


class SetSessionPlay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


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


def _is_one_live_unique_violation(exc: IntegrityError) -> bool:
    orig = getattr(exc, "orig", None)
    name = getattr(orig, "constraint_name", None) if orig is not None else None
    if name == "ux_sessions_one_live":
        return True
    blob = " ".join((str(exc), str(orig) if orig is not None else ""))
    return "ux_sessions_one_live" in blob


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(
    body: CreateSession,
    request: Request,
    db: AsyncSession = SessionDep,
) -> dict[str, Any]:
    # Learn-and-play beta uses observe + settings.play_enabled. Full autonomous mode is Phase 4+.
    if body.mode == "autonomous":
        if not bool(body.settings.get("play_enabled", False)):
            raise TitanError(ErrorCode.NOT_IMPLEMENTED_IN_PHASE, "autonomous mode is Phase 4+")
        body = body.model_copy(update={"mode": "observe"})
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
    # Commit before the response leaves the API. FastAPI runs yield-dep cleanup AFTER
    # the body is sent, so a client that immediately POSTs /start can otherwise 404.
    await db.commit()
    await db.refresh(row)
    if body.auto_start:
        return await _activate_created_session(
            row,
            request=request,
            db=db,
            launch_game=body.launch_game,
        )
    return _session_json(row)


@router.get("/sessions/{session_id}")
async def get_session(session_id: UUID, db: AsyncSession = SessionDep) -> dict[str, Any]:
    row = await _session_or_404(db, session_id)
    return _session_json(row)


@router.get("/play/readiness")
async def play_readiness(
    game_slug: Annotated[str, Query(description="ksp | ets2 | ats")],
    source: Annotated[str, Query(description="live | fixture")] = "live",
) -> dict[str, Any]:
    """Probe kRPC/SCS/HIL attach readiness before starting a learn-and-play session."""
    from typing import Literal

    session_source: Literal["live", "fixture"] = "fixture" if source.strip().lower() == "fixture" else "live"
    attach = probe_attach(game_slug=game_slug, source=session_source)
    return {"play_attach": attach.as_dict()}


async def _activate_created_session(
    row: Session,
    *,
    request: Request,
    db: AsyncSession,
    launch_game: bool,
) -> dict[str, Any]:
    """Move a `created` row to `live` (shared by /start and create auto_start)."""
    session_id = row.id
    if row.state in {"starting", "live", "paused", "stopping"}:
        raise TitanError(ErrorCode.SESSION_ALREADY_LIVE, "session already active")
    if row.state != "created":
        raise TitanError(ErrorCode.INVALID_STATE_TRANSITION, f"cannot start from state {row.state!r}")
    controller = request.app.state.session_controller
    await supersede_other_live_sessions(db, controller, exclude_id=session_id)
    row.state = "starting"
    row.started_at = utc_now()
    if row.clock_origin_mono_ns is None:
        clock = SessionClock.start()
        row.clock_origin_mono_ns = clock.origin_mono_ns
        row.clock_origin_wall = clock.origin_wall
    game_row = await db.scalar(select(Game).where(Game.id == row.game_id))
    game_slug = game_row.slug if game_row is not None else "ksp"
    play_enabled = bool(row.settings.get("play_enabled", False))

    profile: GameProfile | None = None
    if row.game_profile_id is not None:
        profile = await db.scalar(select(GameProfile).where(GameProfile.id == row.game_profile_id))
    default_profile: GameProfile | None = None
    if profile is None:
        default_profile = await db.scalar(
            select(GameProfile)
            .where(GameProfile.game_id == row.game_id, GameProfile.is_default.is_(True))
            .limit(1)
        )
    install_profile = profile or default_profile
    has_install = install_profile is not None
    session_source = resolve_session_source(
        session_source=str(row.settings.get("session_source") or "") or None,
        demo_telemetry=bool(row.settings.get("demo_telemetry", False)),
        has_install=has_install,
    )

    # Launch before attach wait so kRPC/SCS have time to come up with the game.
    launched_game = False
    launch_error: str | None = None
    launched_pid: int | None = None
    if launch_game and profile is not None:
        exe = profile.executable_path

        def _launch() -> tuple[int | None, str | None]:
            path = Path(exe)
            if not path.is_file():
                return None, f"executable not found: {exe}"
            try:
                proc = subprocess.Popen(game_process_argv(exe))  # noqa: S603
            except OSError as exc:
                return None, f"{type(exc).__name__}: {exc}"
            return proc.pid, None

        launched_pid, launch_error = await asyncio.to_thread(_launch)
        launched_game = launch_error is None

    play_attach = None
    play_actions = False
    if play_enabled:
        if session_source == "live":
            play_attach = await wait_probe_attach(
                game_slug=game_slug,
                source=session_source,
                launched_game=launched_game,
            )
        else:
            play_attach = probe_attach(game_slug=game_slug, source=session_source)
        # Only start titan-actions when attach is ready; otherwise stay in observe/learn.
        play_actions = bool(play_attach.ready)
        settings = dict(row.settings or {})
        settings["session_source"] = session_source
        settings["play_attach"] = play_attach.as_dict()
        settings["play_enabled"] = play_enabled
        if not play_actions:
            settings["play_waiting"] = True
        else:
            settings.pop("play_waiting", None)
        row.settings = settings

    try:
        await db.flush()
        # The play loop loads its skip list once, from this session's notes.
        # Write missed contracts before that process starts, then commit them.
        if row.settings.get("agents_enabled", True):
            await seed_prior_memories_on_blackboard(db, session_id=session_id, game_slug=game_slug)
        row.state = "live"
        await db.flush()
    except IntegrityError as exc:
        if _is_one_live_unique_violation(exc):
            raise TitanError(
                ErrorCode.SESSION_ALREADY_LIVE,
                "Another session is still live (ux_sessions_one_live). Stop it or retry start.",
            ) from exc
        raise
    demo_line = session_source == "fixture" or bool(row.settings.get("demo_telemetry", False))
    if not demo_line and install_profile is None:
        demo_line = fixture_fallback_path(game_slug) is not None
    if demo_line:
        await _seed_director_demo_line(db, session_id)
    recording_payload: dict[str, object] | None = None
    recording_error: str | None = None
    if row.settings.get("record_on_start"):
        from titan_api.recording_ops import start_session_recording

        try:
            recording_payload = await start_session_recording(db, row)
        except TitanError as exc:
            if exc.dependency != "obs":
                raise
            # Session start still succeeds. REC does not write a stub timeline when OBS is down.
            recording_error = exc.detail
    # Commit the skip list before the crew starts. The flight loop reads it once.
    await db.commit()
    await db.refresh(row)
    if row.settings.get("agents_enabled", True):
        controller.start_orchestrator(
            session_id,
            game_slug=game_slug,
            play_enabled=play_actions,
            data_dir=row.data_dir,
        )
    if play_actions and play_attach is not None:
        # Explicit backend: hil for fixture, krpc/scs when an install is attached and ready.
        controller.start_actions(
            session_id,
            game_slug=game_slug,
            data_dir=row.data_dir,
            play_backend=play_attach.backend,
        )
    if session_source == "fixture" or row.settings.get("demo_telemetry", False):
        await start_demo_replay(session_id)
    elif install_profile is not None:
        await start_live_telemetry(session_id, game_slug=game_slug, install_path=install_profile.install_path)
    elif fixture_fallback_path(game_slug) is not None:
        await start_demo_replay(session_id)
    payload = _session_json(row)
    if play_attach is not None:
        payload["play_attach"] = play_attach.as_dict()
    payload["session_source"] = session_source
    payload["play_enabled"] = play_enabled
    payload["play_actions"] = play_actions
    payload["game_pid"] = launched_pid
    if launch_error is not None:
        payload["launch_error"] = launch_error
    if recording_payload is not None:
        payload["recording"] = recording_payload
    if recording_error is not None:
        payload["recording_error"] = recording_error
    return payload


@router.post("/sessions/{session_id}/start", status_code=status.HTTP_202_ACCEPTED)
async def start_session(
    session_id: UUID,
    body: StartSession,
    request: Request,
    db: AsyncSession = SessionDep,
) -> dict[str, Any]:
    row = await _session_or_404(db, session_id)
    return await _activate_created_session(row, request=request, db=db, launch_game=body.launch_game)


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


@router.post("/sessions/{session_id}/play", status_code=status.HTTP_202_ACCEPTED)
async def set_session_play(
    session_id: UUID,
    body: SetSessionPlay,
    request: Request,
    db: AsyncSession = SessionDep,
) -> dict[str, Any]:
    """Enable or disable agent play on a live session (attach/detach titan-actions)."""
    row = await _session_or_404(db, session_id)
    if row.state != "live":
        raise TitanError(ErrorCode.INVALID_STATE_TRANSITION, "play can only toggle on a live session")
    controller = request.app.state.session_controller
    game_row = await db.scalar(select(Game).where(Game.id == row.game_id))
    game_slug = game_row.slug if game_row is not None else "ksp"

    profile: GameProfile | None = None
    if row.game_profile_id is not None:
        profile = await db.scalar(select(GameProfile).where(GameProfile.id == row.game_profile_id))
    default_profile: GameProfile | None = None
    if profile is None:
        default_profile = await db.scalar(
            select(GameProfile)
            .where(GameProfile.game_id == row.game_id, GameProfile.is_default.is_(True))
            .limit(1)
        )
    has_install = (profile or default_profile) is not None
    session_source = resolve_session_source(
        session_source=str(row.settings.get("session_source") or "") or None,
        demo_telemetry=bool(row.settings.get("demo_telemetry", False)),
        has_install=has_install,
    )

    settings = dict(row.settings or {})
    settings["play_enabled"] = body.enabled
    settings["session_source"] = session_source
    play_attach = None
    play_actions = False
    if body.enabled:
        if session_source == "live":
            play_attach = await wait_probe_attach(
                game_slug=game_slug,
                source=session_source,
                launched_game=False,
            )
        else:
            play_attach = probe_attach(game_slug=game_slug, source=session_source)
        settings["play_attach"] = play_attach.as_dict()
        play_actions = bool(play_attach.ready)
        if play_actions:
            settings.pop("play_waiting", None)
            # Restart orchestrator so TITAN_SESSION_PLAY=1 wires proposal + feedback loops.
            if row.settings.get("agents_enabled", True):
                controller.restart_orchestrator(
                    session_id,
                    game_slug=game_slug,
                    play_enabled=True,
                    data_dir=row.data_dir,
                )
            controller.stop_actions(session_id)
            controller.start_actions(
                session_id,
                game_slug=game_slug,
                data_dir=row.data_dir,
                play_backend=play_attach.backend,
            )
        else:
            settings["play_waiting"] = True
            controller.stop_actions(session_id)
            if row.settings.get("agents_enabled", True):
                controller.restart_orchestrator(
                    session_id,
                    game_slug=game_slug,
                    play_enabled=False,
                    data_dir=row.data_dir,
                )
    else:
        controller.stop_actions(session_id)
        settings.pop("play_attach", None)
        settings.pop("play_waiting", None)
    row.settings = settings
    await db.flush()
    payload = _session_json(row)
    payload["session_source"] = session_source
    if play_attach is not None:
        payload["play_attach"] = play_attach.as_dict()
    payload["play_enabled"] = body.enabled
    payload["play_actions"] = play_actions
    return payload


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
    controller = request.app.state.session_controller
    row.state = "stopping"
    end_session_row(row, controller, outcome=body.outcome)
    game_row = await db.scalar(select(Game).where(Game.id == row.game_id))
    game_slug = game_row.slug if game_row is not None else "ksp"
    memory_result = await write_learning_on_session_end(
        db,
        session_id=session_id,
        game_slug=game_slug,
        session_title=row.title,
        outcome=body.outcome,
    )
    await db.flush()
    payload = _session_json(row)
    if memory_result.get("written"):
        payload["memory_persist"] = memory_result
    return payload


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

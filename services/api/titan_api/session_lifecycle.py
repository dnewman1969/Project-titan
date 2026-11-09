"""Shared session end/supersede helpers (ux_sessions_one_live, kill switch)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from titan_api.demo_replay import stop_demo_replay
from titan_api.session_telemetry import stop_all_session_telemetry
from titan_core.clock import utc_now
from titan_core.logging import get_logger
from titan_db.models.sessions import Session

if TYPE_CHECKING:
    from titan_api.session_controller import SessionController

log = get_logger(__name__)

LIVE_STATES = frozenset({"starting", "live", "paused", "stopping"})


async def other_live_sessions(db: AsyncSession, *, exclude_id: UUID | None = None) -> list[Session]:
    stmt = select(Session).where(Session.state.in_(LIVE_STATES), Session.mode != "replay")
    if exclude_id is not None:
        stmt = stmt.where(Session.id != exclude_id)
    return list((await db.scalars(stmt)).all())


def end_session_row(
    row: Session,
    controller: SessionController,
    *,
    outcome: str | None,
) -> None:
    if row.state in {"ended", "failed"}:
        return
    stop_demo_replay(row.id)
    stop_all_session_telemetry(row.id)
    controller.stop_actions(row.id)
    controller.stop_orchestrator(row.id)
    row.state = "ended"
    row.ended_at = utc_now()
    row.outcome = outcome


async def supersede_other_live_sessions(
    db: AsyncSession,
    controller: SessionController,
    *,
    exclude_id: UUID,
    outcome: str = "aborted",
) -> list[UUID]:
    """End any other active session so ux_sessions_one_live allows a new live session."""
    ended: list[UUID] = []
    for other in await other_live_sessions(db, exclude_id=exclude_id):
        end_session_row(other, controller, outcome=outcome)
        ended.append(other.id)
    if ended:
        await db.flush()
    return ended


async def end_all_live_sessions(db: AsyncSession, controller: SessionController) -> list[UUID]:
    ended: list[UUID] = []
    for row in await other_live_sessions(db, exclude_id=None):
        end_session_row(row, controller, outcome="aborted")
        ended.append(row.id)
    if ended:
        await db.flush()
    return ended


async def end_live_sessions_for_app(app: FastAPI) -> list[UUID]:
    """End every row counted by ux_sessions_one_live (kill switch, resume, supersede)."""
    factory: Any = app.state.session_factory
    if factory is None:
        return []
    controller = app.state.session_controller
    try:
        async with factory() as db:
            ended = await end_all_live_sessions(db, controller)
            if ended:
                log.info("ended_live_sessions", count=len(ended), session_ids=[str(x) for x in ended])
            await db.commit()
            return ended
    except Exception as exc:
        log.error("end_live_sessions_for_app_failed", error=type(exc).__name__, exc_info=exc)
        return []

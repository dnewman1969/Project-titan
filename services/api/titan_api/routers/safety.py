"""Safety routes (Section 5.2, "Safety")."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from titan_core.logging import get_logger

from titan_api.auth import Authenticated
from titan_api.safety import SafetyController
from titan_api.session_lifecycle import end_all_live_sessions
from titan_core.errors import ErrorCode, TitanError
from titan_core.protocol.system import SafetyArmRequest, SafetyKillRequest, SafetyResumeRequest
from titan_core.protocol.ws import SafetyState

log = get_logger(__name__)

router = APIRouter(prefix="/safety", tags=["safety"], dependencies=[Authenticated])


def _safety(request: Request) -> SafetyController:
    controller: SafetyController = request.app.state.safety
    return controller


@router.get("/state")
async def safety_state(request: Request) -> SafetyState:
    return _safety(request).state


async def _end_live_sessions_after_kill(request: Request) -> None:
    factory = request.app.state.session_factory
    if factory is None:
        return
    controller = request.app.state.session_controller
    try:
        async with factory() as db:
            ended = await end_all_live_sessions(db, controller)
            if ended:
                log.info("kill_ended_live_sessions", count=len(ended))
            await db.commit()
    except Exception as exc:
        log.error("kill_end_live_sessions_failed", error=type(exc).__name__)


@router.post("/kill")
async def safety_kill(body: SafetyKillRequest, request: Request) -> SafetyState:
    """Must answer in under 50 ms: no awaits before the response."""
    state = _safety(request).kill(body.source)
    asyncio.create_task(_end_live_sessions_after_kill(request))
    return state


@router.post("/resume")
async def safety_resume(body: SafetyResumeRequest, request: Request) -> SafetyState:
    return _safety(request).resume()


@router.post("/arm")
async def safety_arm(body: SafetyArmRequest) -> SafetyState:
    raise TitanError(ErrorCode.SAFETY_LOCKED, "Arming is not available in Phase 1: there is no input path.")

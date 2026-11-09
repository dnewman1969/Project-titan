"""Safety routes (Section 5.2, "Safety")."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Request

from titan_api.auth import Authenticated
from titan_api.safety import SafetyController
from titan_api.session_lifecycle import end_live_sessions_for_app
from titan_core.errors import ErrorCode, TitanError
from titan_core.protocol.system import SafetyArmRequest, SafetyKillRequest, SafetyResumeRequest
from titan_core.protocol.ws import SafetyState

router = APIRouter(prefix="/safety", tags=["safety"], dependencies=[Authenticated])


def _safety(request: Request) -> SafetyController:
    controller: SafetyController = request.app.state.safety
    return controller


@router.get("/state")
async def safety_state(request: Request) -> SafetyState:
    return _safety(request).state


@router.post("/kill")
async def safety_kill(
    body: SafetyKillRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> SafetyState:
    """Must answer in under 50 ms: no awaits before the response."""
    state = _safety(request).kill(body.source)
    background_tasks.add_task(end_live_sessions_for_app, request.app)
    return state


@router.post("/resume")
async def safety_resume(body: SafetyResumeRequest, request: Request) -> SafetyState:
    """Clear kill switch and release ux_sessions_one_live so File → New session can start."""
    await end_live_sessions_for_app(request.app)
    return _safety(request).resume()


@router.post("/arm")
async def safety_arm(body: SafetyArmRequest) -> SafetyState:
    raise TitanError(ErrorCode.SAFETY_LOCKED, "Arming is not available in Phase 1: there is no input path.")

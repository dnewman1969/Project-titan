"""Safety routes (Section 5.2, "Safety")."""

from __future__ import annotations

from fastapi import APIRouter, Request

from titan_api.auth import Authenticated
from titan_api.safety import SafetyController
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
async def safety_kill(body: SafetyKillRequest, request: Request) -> SafetyState:
    """Must answer in under 50 ms: no awaits before the response."""
    return _safety(request).kill(body.source)


@router.post("/resume")
async def safety_resume(body: SafetyResumeRequest, request: Request) -> SafetyState:
    return _safety(request).resume()


@router.post("/arm")
async def safety_arm(body: SafetyArmRequest) -> SafetyState:
    raise TitanError(ErrorCode.SAFETY_LOCKED, "Arming is not available in Phase 1: there is no input path.")

"""Model routes (Section 5.2)."""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, ConfigDict

from titan_api.auth import Authenticated
from titan_core.errors import ErrorCode, TitanError
from titan_models.jobs import PullJobRunner
from titan_models.registry import ModelsRegistry
from titan_models.routing import RoleRoute

router = APIRouter(prefix="/models", tags=["models"], dependencies=[Authenticated])


class PullRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str


class RoutesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: str
    roles: dict[str, dict[str, Any]]


class RoutesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: str
    roles: dict[str, RoleRoute]


def _registry(request: Request) -> ModelsRegistry:
    registry = request.app.state.models_registry
    if registry is None:
        raise TitanError(
            ErrorCode.DEPENDENCY_UNAVAILABLE,
            "Models registry is not configured.",
            dependency="ollama",
        )
    return cast(ModelsRegistry, registry)


def _jobs(request: Request) -> PullJobRunner:
    runner = request.app.state.pull_jobs
    if runner is None:
        raise TitanError(ErrorCode.INTERNAL, "Pull job runner is not configured.")
    return cast(PullJobRunner, runner)


@router.get("")
async def list_models(request: Request) -> dict[str, Any]:
    registry = _registry(request)
    healthy_any = False
    try:
        providers = await registry.list_provider_status()
        healthy_any = any(row["healthy"] for row in providers)
    except Exception as exc:
        raise TitanError(
            ErrorCode.DEPENDENCY_UNAVAILABLE,
            f"Ollama is not reachable ({type(exc).__name__}).",
            dependency="ollama",
        ) from exc
    if not healthy_any and "ollama" in registry.providers:
        raise TitanError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Ollama is not running.", dependency="ollama")
    return {"providers": providers}


@router.get("/routes")
async def get_routes(request: Request) -> RoutesResponse:
    registry = _registry(request)
    roles = {
        name: {
            "provider": route.provider,
            "model": route.model,
            **({"params": route.params.model_dump(exclude_none=True)} if route.params else {}),
        }
        for name, route in registry.roles().items()
    }
    return RoutesResponse(profile=registry.config.profile, roles=roles)


@router.put("/routes")
async def put_routes(body: RoutesUpdate, request: Request) -> RoutesResponse:
    registry = _registry(request)
    registry.set_profile(body.profile)
    errors = await registry.validate_roles(body.roles)
    if errors:
        raise TitanError(
            ErrorCode.VALIDATION_FAILED,
            "Route validation failed.",
            errors=[{"message": e} for e in errors],
        )
    registry.update_roles(body.roles)
    registry.persist()
    return await get_routes(request)


@router.post("/pull", status_code=status.HTTP_202_ACCEPTED)
async def pull_model(body: PullRequest, request: Request) -> dict[str, str]:
    registry = _registry(request)
    if body.provider not in registry.providers:
        raise TitanError(ErrorCode.VALIDATION_FAILED, f"Unknown provider {body.provider!r}.")
    provider = registry.provider_for(body.provider)
    if not await provider.health():
        raise TitanError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Ollama is not running.", dependency="ollama")
    job_id = await _jobs(request).start_pull(body.provider, body.model)
    return {"job_id": str(job_id)}

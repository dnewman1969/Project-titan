"""Games and discovery routes (Section 5.2)."""

from __future__ import annotations

import platform
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from titan_api.auth import Authenticated
from titan_api.deps import db_session
from titan_api.game_launch import game_process_argv
from titan_api.games_sync import sync_games_from_catalog
from titan_core.clock import utc_now
from titan_core.errors import ErrorCode, TitanError
from titan_core.ids import uuid7
from titan_db.models.games import Game, GameProfile
from titan_db.models.knowledge import ControlBinding, RiskEntry, Strategy
from titan_sdk_games.adapter import GameAdapter
from titan_sdk_games.catalog import GameCatalog
from titan_sdk_games.discovery.windows_defaults import enrich_discovery_context
from titan_sdk_games.profiles import GameProfile as AdapterProfile
from titan_sdk_games.types import Consent

router = APIRouter(tags=["games"], dependencies=[Authenticated])

SessionDep = Depends(db_session)


class ScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stores: list[str] = Field(default_factory=lambda: ["steam", "epic", "gog"])
    extra_paths: list[str] = Field(default_factory=list)


class ProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_default: bool | None = None
    launch_args: list[str] | None = None


class ProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game_slug: str
    executable_path: str


class InstallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    consent: bool


class ControlBindingBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str
    action_label: str
    context: str = "default"
    device: str
    binding: dict[str, Any]
    action_class: str
    source: str = "user"
    confidence: float = 1.0


def _catalog(request: Request) -> GameCatalog:
    catalog = request.app.state.game_catalog
    return cast(GameCatalog, catalog)


def _platform() -> str:
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    if system == "darwin":
        return "darwin"
    return "linux"


def _serialize_game(row: Game, *, include_profiles: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(row.id),
        "slug": row.slug,
        "name": row.name,
        "domain": row.domain,
        "genres": row.genres,
        "capabilities": row.capabilities,
        "research_status": row.research_status,
    }
    if include_profiles:
        payload["profiles"] = [_serialize_profile(p) for p in row.profiles]
    return payload


def _serialize_profile(row: GameProfile) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "game_id": str(row.game_id),
        "store": row.store,
        "install_path": row.install_path,
        "executable_path": row.executable_path,
        "game_version": row.game_version,
        "telemetry_status": row.telemetry_status,
        "is_default": row.is_default,
        "last_seen_at": row.last_seen_at.isoformat() if row.last_seen_at else None,
    }


async def _game_or_404(session: AsyncSession, game_id: UUID) -> Game:
    row = await session.scalar(select(Game).options(selectinload(Game.profiles)).where(Game.id == game_id))
    if row is None:
        raise TitanError(ErrorCode.NOT_FOUND, f"Game {game_id} not found.")
    return row


async def _profile_or_404(session: AsyncSession, profile_id: UUID) -> GameProfile:
    row = await session.scalar(
        select(GameProfile).options(selectinload(GameProfile.game)).where(GameProfile.id == profile_id)
    )
    if row is None:
        raise TitanError(ErrorCode.NOT_FOUND, f"Game profile {profile_id} not found.")
    return row


def _adapter_for_game(catalog: GameCatalog, game: Game) -> type[GameAdapter]:
    found = catalog.get(game.slug)
    if found is None:
        raise TitanError(ErrorCode.NOT_FOUND, f"No adapter registered for slug {game.slug!r}.")
    return found


@router.get("/games")
async def list_games(
    request: Request,
    session: AsyncSession = SessionDep,
    include_profiles: Annotated[bool, Query(alias="include_profiles")] = False,
) -> dict[str, Any]:
    catalog = _catalog(request)
    catalog.reload()
    await sync_games_from_catalog(session, catalog)
    rows = (
        await session.scalars(select(Game).options(selectinload(Game.profiles)).order_by(Game.name))
    ).all()
    return {"items": [_serialize_game(row, include_profiles=include_profiles) for row in rows]}


@router.post("/games/scan")
async def scan_games(
    body: ScanRequest,
    request: Request,
    session: AsyncSession = SessionDep,
) -> dict[str, Any]:
    catalog = _catalog(request)
    catalog.reload()
    await sync_games_from_catalog(session, catalog)
    ctx = enrich_discovery_context(
        platform=_platform(),
        extra_paths=[Path(p) for p in body.extra_paths],
    )
    detected: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    games = (await session.scalars(select(Game))).all()
    slug_to_game = {g.slug: g for g in games}
    for adapter_cls in (catalog.get(g.slug) for g in games):
        if adapter_cls is None:
            continue
        for hit in adapter_cls.detect(ctx, stores=body.stores):
            game = slug_to_game.get(hit.game_slug)
            if game is None:
                unmatched.append(hit.model_dump())
                continue
            profile = await _upsert_profile(session, game, hit)
            detected.append(
                {
                    "game_slug": hit.game_slug,
                    "profile_id": str(profile.id),
                    "store": hit.store,
                    "install_path": hit.install_path,
                    "game_version": hit.game_version,
                }
            )
    await session.commit()
    return {
        "detected": detected,
        "unmatched": unmatched,
        "scan_context": {
            "platform": ctx.platform,
            "steam_libraries": [str(p) for p in ctx.steam_libraries],
            "epic_manifest_dirs": [str(p) for p in ctx.epic_manifest_dirs],
            "gog_install_roots": [str(p) for p in ctx.gog_install_roots],
            "extra_paths": [str(p) for p in ctx.extra_paths],
            "stores_scanned": body.stores,
        },
    }


async def _upsert_profile(session: AsyncSession, game: Game, hit: Any) -> GameProfile:
    existing = await session.scalar(
        select(GameProfile).where(
            GameProfile.game_id == game.id,
            GameProfile.install_path == hit.install_path,
        )
    )
    now = utc_now()
    if existing is not None:
        existing.executable_path = hit.executable_path
        existing.game_version = hit.game_version
        existing.last_seen_at = now
        if hit.launch_uri:
            existing.launch_uri = hit.launch_uri
        await session.flush()
        return existing
    profile = GameProfile(
        id=uuid7(),
        game_id=game.id,
        store=hit.store,
        install_path=hit.install_path,
        executable_path=hit.executable_path,
        launch_uri=hit.launch_uri,
        game_version=hit.game_version,
        telemetry_status="unknown",
        is_default=not any(p.is_default for p in game.profiles),
        last_seen_at=now,
    )
    session.add(profile)
    await session.flush()
    return profile


@router.get("/games/{game_id}")
async def get_game(game_id: UUID, session: AsyncSession = SessionDep) -> dict[str, Any]:
    game = await _game_or_404(session, game_id)
    return _serialize_game(game, include_profiles=True)


@router.patch("/game-profiles/{profile_id}")
async def patch_profile(
    profile_id: UUID,
    body: ProfilePatch,
    session: AsyncSession = SessionDep,
) -> dict[str, Any]:
    profile = await _profile_or_404(session, profile_id)
    if body.is_default is True:
        await session.execute(
            update(GameProfile).where(GameProfile.game_id == profile.game_id).values(is_default=False)
        )
        profile.is_default = True
    if body.launch_args is not None:
        profile.launch_args = body.launch_args
    await session.flush()
    return _serialize_profile(profile)


@router.post("/game-profiles", status_code=status.HTTP_201_CREATED)
async def create_profile(
    body: ProfileCreate,
    request: Request,
    session: AsyncSession = SessionDep,
) -> dict[str, Any]:
    catalog = _catalog(request)
    game = await session.scalar(
        select(Game).options(selectinload(Game.profiles)).where(Game.slug == body.game_slug)
    )
    if game is None:
        raise TitanError(ErrorCode.NOT_FOUND, f"Unknown game slug {body.game_slug!r}.")
    exe = Path(body.executable_path)
    if not exe.is_file():  # noqa: ASYNC240
        raise TitanError(ErrorCode.VALIDATION_FAILED, "executable_path must exist.")
    adapter = catalog.get(body.game_slug)
    if adapter is None:
        raise TitanError(ErrorCode.NOT_FOUND, f"No adapter for slug {body.game_slug!r}.")
    from titan_sdk_games.types import DetectedInstall

    hit = DetectedInstall(
        game_slug=body.game_slug,
        store="standalone",
        install_path=str(exe.parent),
        executable_path=str(exe.resolve()),  # noqa: ASYNC240
    )
    profile = await _upsert_profile(session, game, hit)
    await session.commit()
    return _serialize_profile(profile)


@router.get("/game-profiles/{profile_id}/integration")
async def get_integration(
    profile_id: UUID,
    request: Request,
    session: AsyncSession = SessionDep,
) -> dict[str, Any]:
    profile = await _profile_or_404(session, profile_id)
    catalog = _catalog(request)
    adapter_cls = _adapter_for_game(catalog, profile.game)
    status_row = adapter_cls().check_integration(_to_adapter_profile(profile))
    return {
        "status": status_row.status,
        "details": status_row.details,
        "instructions_md": status_row.instructions_md,
    }


@router.post("/game-profiles/{profile_id}/integration/install")
async def install_integration(
    profile_id: UUID,
    body: InstallRequest,
    request: Request,
    session: AsyncSession = SessionDep,
) -> dict[str, Any]:
    profile = await _profile_or_404(session, profile_id)
    catalog = _catalog(request)
    adapter_cls = _adapter_for_game(catalog, profile.game)
    result = adapter_cls().install_integration(
        _to_adapter_profile(profile),
        Consent(granted=body.consent),
    )
    if result.status == "failed" and result.details.get("reason") == "consent_required":
        raise TitanError(ErrorCode.VALIDATION_FAILED, "Consent is required.")
    if result.status == "outdated" and result.details.get("expected"):
        raise TitanError(ErrorCode.VERSION_MISMATCH, "Integration hash mismatch.", title="Hash mismatch")
    profile.telemetry_status = result.status
    profile.telemetry_details = result.details
    await session.flush()
    return {"status": result.status}


@router.post("/game-profiles/{profile_id}/launch", status_code=status.HTTP_202_ACCEPTED)
async def launch_profile(
    profile_id: UUID,
    request: Request,
    session: AsyncSession = SessionDep,
) -> dict[str, Any]:
    profile = await _profile_or_404(session, profile_id)
    catalog = _catalog(request)
    adapter_cls = _adapter_for_game(catalog, profile.game)
    manifest = adapter_cls.load_manifest()
    method = "steam_uri" if manifest.launch.steam_uri else "executable"
    pid: int | None = None
    if _platform() == "windows" and method == "executable" and Path(profile.executable_path).is_file():  # noqa: ASYNC240
        proc = subprocess.Popen(game_process_argv(profile.executable_path))  # noqa: ASYNC220, S603
        pid = proc.pid
    return {"pid": pid, "method": method}


@router.get("/games/{game_id}/controls")
async def list_controls(
    game_id: UUID,
    request: Request,
    context: str | None = None,
    session: AsyncSession = SessionDep,
) -> dict[str, Any]:
    game = await _game_or_404(session, game_id)
    catalog = _catalog(request)
    adapter_cls = catalog.get(game.slug)
    query = select(ControlBinding).where(ControlBinding.game_id == game.id)
    if context:
        query = query.where(ControlBinding.context == context)
    rows = (await session.scalars(query)).all()
    if not rows and adapter_cls is not None:
        default_profile = next((p for p in game.profiles if p.is_default), None)
        if default_profile is not None:
            parsed = adapter_cls().parse_controls(_to_adapter_profile(default_profile))
            return {"items": [b.model_dump() for b in parsed if context is None or b.context == context]}
    return {
        "items": [
            {
                "id": str(row.id),
                "action_id": row.action_id,
                "action_label": row.action_label,
                "context": row.context,
                "device": row.device,
                "binding": row.binding,
                "action_class": row.action_class,
                "source": row.source,
                "confidence": row.confidence,
            }
            for row in rows
        ]
    }


@router.put("/games/{game_id}/controls/{binding_id}")
async def put_control(
    game_id: UUID,
    binding_id: UUID,
    body: ControlBindingBody,
    session: AsyncSession = SessionDep,
) -> dict[str, Any]:
    row = await session.scalar(
        select(ControlBinding).where(ControlBinding.id == binding_id, ControlBinding.game_id == game_id)
    )
    if row is None:
        raise TitanError(ErrorCode.NOT_FOUND, "Control binding not found.")
    row.action_id = body.action_id
    row.action_label = body.action_label
    row.context = body.context
    row.device = body.device
    row.binding = body.binding
    row.action_class = body.action_class
    row.source = "user"
    row.confidence = body.confidence
    row.updated_at = datetime.now(tz=UTC)
    await session.flush()
    return {
        "id": str(row.id),
        "action_id": row.action_id,
        "action_label": row.action_label,
        "context": row.context,
        "device": row.device,
        "binding": row.binding,
        "action_class": row.action_class,
        "source": row.source,
        "confidence": row.confidence,
    }


@router.get("/games/{game_id}/risks")
async def list_risks(game_id: UUID, session: AsyncSession = SessionDep) -> dict[str, Any]:
    await _game_or_404(session, game_id)
    rows = (
        await session.scalars(select(RiskEntry).where(RiskEntry.game_id == game_id).order_by(RiskEntry.title))
    ).all()
    return {
        "items": [
            {
                "id": str(row.id),
                "title": row.title,
                "description": row.description,
                "category": row.category,
                "severity": row.severity,
                "likelihood": row.likelihood,
            }
            for row in rows
        ]
    }


@router.get("/games/{game_id}/strategies")
async def list_strategies(
    game_id: UUID,
    status: str | None = Query(default=None, alias="status"),
    session: AsyncSession = SessionDep,
) -> dict[str, Any]:
    await _game_or_404(session, game_id)
    query = select(Strategy).where(Strategy.game_id == game_id)
    if status:
        query = query.where(Strategy.status == status)
    rows = (await session.scalars(query.order_by(Strategy.title))).all()
    return {
        "items": [
            {
                "id": str(row.id),
                "title": row.title,
                "level": row.level,
                "situation": row.situation,
                "status": row.status,
            }
            for row in rows
        ]
    }


def _to_adapter_profile(row: GameProfile) -> AdapterProfile:
    return AdapterProfile(
        id=row.id,
        game_id=row.game_id,
        store=row.store,
        install_path=row.install_path,
        executable_path=row.executable_path,
        launch_uri=row.launch_uri,
        launch_args=list(row.launch_args),
        game_version=row.game_version,
        config_paths=list(row.config_paths) if isinstance(row.config_paths, list) else [],
    )

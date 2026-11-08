"""Settings routes (Section 5.2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from titan_api.auth import Authenticated
from titan_api.deps import db_session
from titan_db.repositories.settings import SettingsRepository

router = APIRouter(prefix="/settings", tags=["settings"], dependencies=[Authenticated])


@router.get("")
async def get_settings(session: AsyncSession = Depends(db_session)) -> dict[str, Any]:  # noqa: B008
    repo = SettingsRepository(session)
    return (await repo.get()).model_dump()


@router.patch("")
async def patch_settings(
    patch: dict[str, Any],
    session: AsyncSession = Depends(db_session),  # noqa: B008
    if_match: int = Header(alias="If-Match"),
) -> dict[str, Any]:
    repo = SettingsRepository(session)
    return (await repo.patch(patch, expected_version=if_match)).model_dump()

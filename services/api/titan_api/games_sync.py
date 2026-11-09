"""Upsert ORM `games` rows from installed `titan.games` entry points."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from titan_core.ids import uuid7
from titan_db.models.games import Game
from titan_db.transaction import transaction
from titan_sdk_games.catalog import GameCatalog


async def sync_games_from_catalog(session: AsyncSession, catalog: GameCatalog) -> int:
    count = 0
    async with transaction(session):
        for ep_name, adapter_cls in catalog.adapters.items():
            manifest = adapter_cls.load_manifest()
            existing_id = await session.scalar(select(Game.id).where(Game.slug == manifest.id))
            row: dict[str, Any] = {
                "id": existing_id or uuid7(),
                "slug": manifest.id,
                "name": manifest.name,
                "adapter_id": ep_name,
                "adapter_version": manifest.adapter_version,
                "domain": manifest.domain,
                "genres": manifest.genre,
                "capabilities": manifest.capabilities.model_dump(),
                "store_ids": manifest.store_ids(),
                "research_status": "none",
                "manifest": manifest.model_dump(mode="json"),
            }
            stmt = insert(Game).values(**row)
            stmt = stmt.on_conflict_do_update(
                index_elements=[Game.slug],
                set_={
                    "name": stmt.excluded.name,
                    "adapter_id": stmt.excluded.adapter_id,
                    "adapter_version": stmt.excluded.adapter_version,
                    "domain": stmt.excluded.domain,
                    "genres": stmt.excluded.genres,
                    "capabilities": stmt.excluded.capabilities,
                    "store_ids": stmt.excluded.store_ids,
                    "manifest": stmt.excluded.manifest,
                },
            )
            await session.execute(stmt)
            count += 1
    return count

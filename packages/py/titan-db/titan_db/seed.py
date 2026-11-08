"""Seed built-in games, personas, and default teams (M2.T4, Appendix A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import yaml
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from titan_core.ids import uuid7
from titan_db.models.agents import Agent, AgentPersona, AgentTeam
from titan_db.models.games import Game
from titan_db.transaction import transaction

REPO_ROOT = Path(__file__).resolve().parents[4]
PERSONAS_DIR = REPO_ROOT / "config" / "personas"
GAMES_DIR = REPO_ROOT / "games"
PROMPT_FILE = PERSONAS_DIR / "_prompt.txt"

DOMAIN_MAP = {
    "space": "space",
    "ground_vehicle": "ground_vehicle",
}


async def seed_all(factory: async_sessionmaker[AsyncSession]) -> dict[str, int]:
    prompt = PROMPT_FILE.read_text(encoding="utf-8")
    async with factory() as session, transaction(session):
        personas = await _seed_personas(session, prompt)
        games = await _seed_games(session)
        teams = await _seed_teams(session, games, personas)
    return {"personas": personas, "games": games, "teams": teams}


async def _seed_personas(session: AsyncSession, prompt_template: str) -> int:
    count = 0
    for path in sorted(PERSONAS_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or "slug" not in data:
            continue
        row = {
            "id": await _persona_id(session, data["slug"]) or uuid7(),
            "slug": data["slug"],
            "display_name": data["display_name"],
            "role": data["role"],
            "department": data["department"],
            "personality": data.get("personality", {}),
            "backstory": data.get("backstory"),
            "speaking_style": data.get("speaking_style"),
            "system_prompt_template": prompt_template,
            "color_hex": data.get("color_hex", "#888888"),
            "model_role": data.get("model_role", "agent"),
            "game_id": None,
            "source": "builtin",
            "version": 1,
        }
        stmt = insert(AgentPersona).values(**row)
        stmt = stmt.on_conflict_do_update(
            index_elements=[AgentPersona.slug],
            set_={
                "display_name": stmt.excluded.display_name,
                "role": stmt.excluded.role,
                "department": stmt.excluded.department,
                "personality": stmt.excluded.personality,
                "backstory": stmt.excluded.backstory,
                "speaking_style": stmt.excluded.speaking_style,
                "system_prompt_template": stmt.excluded.system_prompt_template,
                "color_hex": stmt.excluded.color_hex,
                "model_role": stmt.excluded.model_role,
            },
        )
        await session.execute(stmt)
        count += 1
    return count


async def _persona_id(session: AsyncSession, slug: str) -> UUID | None:
    return await session.scalar(select(AgentPersona.id).where(AgentPersona.slug == slug))


async def _seed_games(session: AsyncSession) -> int:
    count = 0
    for slug in ("ksp", "ets2", "ats"):
        manifest_path = GAMES_DIR / slug / "titan-game.yaml"
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise TypeError(f"{manifest_path}: expected mapping")
        row = {
            "id": await _game_id(session, slug) or uuid7(),
            "slug": slug,
            "name": manifest["name"],
            "adapter_id": manifest["id"],
            "adapter_version": manifest["adapter_version"],
            "domain": manifest["domain"],
            "genres": manifest.get("genre", []),
            "capabilities": manifest.get("capabilities", {}),
            "store_ids": _store_ids(manifest),
            "research_status": "none",
            "manifest": manifest,
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


def _store_ids(manifest: dict[str, Any]) -> dict[str, Any]:
    detection = manifest.get("detection", {})
    return {
        "steam": detection.get("steam_app_ids", []),
        "epic": detection.get("epic_catalog_ids", []),
        "gog": detection.get("gog_product_ids", []),
    }


async def _game_id(session: AsyncSession, slug: str) -> UUID | None:
    return await session.scalar(select(Game.id).where(Game.slug == slug))


async def _seed_teams(session: AsyncSession, games: int, personas: int) -> int:
    del personas  # personas must exist before agents link to them
    count = 0
    for slug in ("ksp", "ets2", "ats"):
        game_id = await _game_id(session, slug)
        if game_id is None:
            continue
        team_path = GAMES_DIR / slug / "teams" / "default.yaml"
        team = yaml.safe_load(team_path.read_text(encoding="utf-8"))
        if not isinstance(team, dict):
            raise TypeError(f"{team_path}: expected mapping")
        team_id = await _team_id(session, game_id, team["name"], version=1) or uuid7()
        team_row = {
            "id": team_id,
            "game_id": game_id,
            "name": team["name"],
            "purpose": team["purpose"],
            "template_slug": team.get("template_slug"),
            "source": "builtin",
            "version": 1,
            "is_active": True,
        }
        stmt = insert(AgentTeam).values(**team_row)
        stmt = stmt.on_conflict_do_update(
            constraint="agent_teams_game_id_name_version_key",
            set_={
                "purpose": stmt.excluded.purpose,
                "template_slug": stmt.excluded.template_slug,
                "is_active": stmt.excluded.is_active,
            },
        )
        await session.execute(stmt)
        for spec in team.get("agents", []):
            persona_id = await _persona_id(session, spec["persona_slug"])
            if persona_id is None:
                continue
            agent_row = {
                "id": uuid7(),
                "team_id": team_id,
                "persona_id": persona_id,
                "role": spec["role"],
                "is_director": bool(spec.get("is_director", False)),
                "event_subscriptions": spec.get("event_subscriptions", []),
                "tick_interval_ms": spec.get("tick_interval_ms", 10000),
                "can_commentate": True,
                "can_act": False,
                "status": "active",
            }
            stmt_a = insert(Agent).values(**agent_row)
            stmt_a = stmt_a.on_conflict_do_update(
                constraint="agents_team_id_role_key",
                set_={
                    "persona_id": stmt_a.excluded.persona_id,
                    "is_director": stmt_a.excluded.is_director,
                    "event_subscriptions": stmt_a.excluded.event_subscriptions,
                    "tick_interval_ms": stmt_a.excluded.tick_interval_ms,
                },
            )
            await session.execute(stmt_a)
        count += 1
    return count


async def _team_id(session: AsyncSession, game_id: UUID, name: str, *, version: int) -> UUID | None:
    return await session.scalar(
        select(AgentTeam.id).where(
            AgentTeam.game_id == game_id,
            AgentTeam.name == name,
            AgentTeam.version == version,
        )
    )

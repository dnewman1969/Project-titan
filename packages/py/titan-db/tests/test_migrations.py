"""Initial migration tests: matches Section 4.2 verbatim, upgrades and downgrades cleanly, and the
Phase 1 constraints hold (one live session, `approval_required`, `p1_no_actions`, one director)."""

from __future__ import annotations

import re
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import pytest

from titan_db import migrate
from titan_db.sql import created_tables, split_statements
from titan_testing.db import TempDatabase

ROOT = Path(__file__).resolve().parents[4]
SPEC = ROOT / "docs" / "titan-architecture-spec.md"
DDL_FILE = migrate.MIGRATIONS_DIR / "versions" / "0001_initial_schema.sql"

EXPECTED_TABLES = {
    "games", "game_profiles", "agent_personas", "agent_teams", "agents", "sessions", "missions",
    "agent_instances", "tasks", "research_sources", "knowledge_entries", "strategies", "risk_entries",
    "control_bindings", "memories", "blackboard_entries", "events", "agent_messages",
    "telemetry_samples", "llm_calls", "recordings", "recording_tracks", "markers", "video_projects",
    "video_project_sources", "thumbnails", "platform_accounts", "upload_jobs", "analytics_snapshots",
    "settings",
}  # fmt: skip


def spec_ddl() -> str:
    text = SPEC.read_text(encoding="utf-8")
    match = re.search(r"### 4\.2 DDL\s*```sql\n(.*?)```", text, re.DOTALL)
    assert match, "Section 4.2 DDL block not found in the spec"
    return match.group(1)


def test_sql_file_matches_spec_section_4_2_verbatim() -> None:
    assert DDL_FILE.read_text(encoding="utf-8") == spec_ddl(), (
        "0001_initial_schema.sql and spec Section 4.2 differ; change both in the same PR (with an ADR)"
    )


def test_ddl_creates_every_expected_table() -> None:
    assert set(created_tables(DDL_FILE.read_text(encoding="utf-8"))) == EXPECTED_TABLES


@pytest.fixture
def migrated(temp_db: TempDatabase) -> Iterator[TempDatabase]:
    migrate.upgrade(temp_db.url)
    yield temp_db


@pytest.fixture
async def conn(migrated: TempDatabase) -> AsyncIterator[asyncpg.Connection]:
    connection = await migrated.connect()
    try:
        yield connection
    finally:
        await connection.close()


async def _tables(conn: asyncpg.Connection) -> set[str]:
    rows = await conn.fetch(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
    )
    return {r["table_name"] for r in rows} - {"alembic_version"}


@pytest.mark.postgres
async def test_upgrade_creates_schema(conn: asyncpg.Connection) -> None:
    assert await _tables(conn) == EXPECTED_TABLES
    assert await conn.fetchval(
        "SELECT count(*) FROM information_schema.views WHERE table_name = 'blackboard_current'"
    )
    assert await conn.fetchval("SELECT count(*) FROM information_schema.schemata WHERE schema_name = 'lg'")
    assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0001"
    triggers = {
        r["event_object_table"]
        for r in await conn.fetch(
            "SELECT event_object_table FROM information_schema.triggers WHERE trigger_name LIKE 'trg_%_updated'"
        )
    }
    with_updated_at = {
        r["table_name"]
        for r in await conn.fetch(
            "SELECT table_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name = 'updated_at' AND table_name <> 'blackboard_current'"
        )
    }
    assert triggers == with_updated_at


@pytest.mark.postgres
def test_downgrade_base_then_upgrade_again(migrated: TempDatabase) -> None:
    import asyncio

    async def count_tables() -> int:
        c = await migrated.connect()
        try:
            return len(await _tables(c))
        finally:
            await c.close()

    migrate.downgrade(migrated.url, "base")
    assert asyncio.run(count_tables()) == 0
    migrate.upgrade(migrated.url, "head")
    assert asyncio.run(count_tables()) == len(EXPECTED_TABLES)


def _id() -> uuid.UUID:
    return uuid.uuid4()


async def _game(conn: asyncpg.Connection) -> uuid.UUID:
    gid = _id()
    await conn.execute(
        "INSERT INTO games (id, slug, name, adapter_id, adapter_version, domain, manifest) "
        "VALUES ($1, 'ksp', 'Kerbal Space Program', 'ksp', '1.0.0', 'space', '{}')",
        gid,
    )
    return gid


async def _session(conn: asyncpg.Connection, game_id: uuid.UUID, state: str, mode: str = "observe") -> None:
    await conn.execute(
        "INSERT INTO sessions (id, game_id, state, mode, data_dir) VALUES ($1, $2, $3, $4, '/tmp/s')",
        _id(),
        game_id,
        state,
        mode,
    )


@pytest.mark.postgres
async def test_only_one_live_session(conn: asyncpg.Connection) -> None:
    gid = await _game(conn)
    await _session(conn, gid, "live")
    await _session(conn, gid, "ended")
    await _session(conn, gid, "live", mode="replay")  # replays do not count
    with pytest.raises(asyncpg.UniqueViolationError):
        await _session(conn, gid, "starting")


async def _team_with_persona(conn: asyncpg.Connection, game_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    team, persona = _id(), _id()
    await conn.execute(
        "INSERT INTO agent_teams (id, game_id, name, purpose, source) VALUES ($1, $2, 'Mission Control', 'p', 'builtin')",
        team,
        game_id,
    )
    await conn.execute(
        "INSERT INTO agent_personas (id, slug, display_name, role, department, personality, "
        "system_prompt_template, source) VALUES ($1, 'ksp.director.wernher', 'Wernher', 'director', "
        "'director', '{}', 'x', 'builtin')",
        persona,
    )
    return team, persona


async def _agent(
    conn: asyncpg.Connection, team: uuid.UUID, persona: uuid.UUID, role: str, *, director: bool, can_act: bool
) -> None:
    await conn.execute(
        "INSERT INTO agents (id, team_id, persona_id, role, is_director, can_act) VALUES ($1, $2, $3, $4, $5, $6)",
        _id(),
        team,
        persona,
        role,
        director,
        can_act,
    )


@pytest.mark.postgres
async def test_agents_cannot_act_in_phase_1(conn: asyncpg.Connection) -> None:
    team, persona = await _team_with_persona(conn, await _game(conn))
    with pytest.raises(asyncpg.CheckViolationError, match="p1_no_actions"):
        await _agent(conn, team, persona, "pilot", director=False, can_act=True)


@pytest.mark.postgres
async def test_one_director_per_team(conn: asyncpg.Connection) -> None:
    team, persona = await _team_with_persona(conn, await _game(conn))
    await _agent(conn, team, persona, "director", director=True, can_act=False)
    await _agent(conn, team, persona, "navigator", director=False, can_act=False)
    with pytest.raises(asyncpg.UniqueViolationError, match="ux_agents_one_director"):
        await _agent(conn, team, persona, "co_director", director=True, can_act=False)


@pytest.mark.postgres
async def test_upload_requires_approval(conn: asyncpg.Connection) -> None:
    project, account = _id(), _id()
    await conn.execute("INSERT INTO video_projects (id, title) VALUES ($1, 'Ep 1')", project)
    await conn.execute(
        "INSERT INTO platform_accounts (id, platform, display_name, remote_channel_id, credential_ref, status) "
        "VALUES ($1, 'youtube', 'Me', 'UC1', 'titan/youtube/UC1', 'connected')",
        account,
    )
    insert = (
        "INSERT INTO upload_jobs (id, video_project_id, account_id, platform, status, metadata, approved_at) "
        "VALUES ($1, $2, $3, 'youtube', $4, '{}', $5)"
    )
    await conn.execute(insert, _id(), project, account, "awaiting_approval", None)
    with pytest.raises(asyncpg.CheckViolationError, match="approval_required"):
        await conn.execute(insert, _id(), project, account, "uploading", None)
    await conn.execute(insert, _id(), project, account, "uploading", await conn.fetchval("SELECT now()"))


@pytest.mark.postgres
async def test_updated_at_trigger(conn: asyncpg.Connection) -> None:
    await conn.execute(
        "INSERT INTO settings (key, value, updated_at) VALUES ('ui.layout', '{}', now() - interval '1 day')"
    )
    before = await conn.fetchval("SELECT updated_at FROM settings WHERE key = 'ui.layout'")
    await conn.execute("UPDATE settings SET value = '{\"a\":1}' WHERE key = 'ui.layout'")
    after = await conn.fetchval("SELECT updated_at FROM settings WHERE key = 'ui.layout'")
    assert after > before


def test_split_statements_keeps_function_bodies() -> None:
    script = (
        "CREATE EXTENSION x;\n"
        "-- a comment; with a semicolon;\n"
        "CREATE FUNCTION f() RETURNS trigger AS $$\n"
        "BEGIN NEW.a = now(); RETURN NEW; END; $$ LANGUAGE plpgsql;\n"
        "CREATE TABLE t (\n  a int -- trailing;\n);\n"
        "SELECT 1"
    )
    statements = split_statements(script)
    assert len(statements) == 4
    assert (
        statements[1].startswith("CREATE FUNCTION")
        and "RETURN NEW; END; $$ LANGUAGE plpgsql" in statements[1]
    )
    assert statements[2] == "CREATE TABLE t (\n  a int \n)"
    assert statements[3] == "SELECT 1"
    assert created_tables(script) == ["t"]


def test_full_ddl_splits_into_expected_statement_count() -> None:
    statements = split_statements(DDL_FILE.read_text(encoding="utf-8"))
    assert sum(s.startswith("CREATE TABLE") for s in statements) == len(EXPECTED_TABLES)
    assert all(not s.endswith(";") for s in statements)

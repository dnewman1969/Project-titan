from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from titan_db.models.realtime import LlmCall
from titan_db.session import create_engine, create_session_factory
from titan_models.llm_calls import make_llm_call_logger
from titan_models.types import ChatResult
from titan_testing.db import TempDatabase

pytestmark = pytest.mark.postgres


@pytest_asyncio.fixture
async def db_factory(migrated_db: TempDatabase) -> async_sessionmaker[AsyncSession]:
    engine = create_engine(migrated_db.pg)
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_llm_call_logger_persists_row(db_factory: async_sessionmaker[AsyncSession]) -> None:
    log = make_llm_call_logger(db_factory)
    await log(
        {
            "session_id": None,
            "priority": 1,
            "model_role": "commentary",
            "purpose": "live",
            "result": ChatResult(
                text="hi",
                tool_calls=[],
                model="fake:small",
                provider="fake",
                prompt_tokens=3,
                completion_tokens=2,
                ttft_ms=10,
                latency_ms=40,
                finish_reason="stop",
            ),
        }
    )
    async with db_factory() as session:
        total = await session.scalar(select(func.count()).select_from(LlmCall))
        assert total == 1

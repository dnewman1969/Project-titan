"""Persist scheduler results to `llm_calls` (Section 2.9.3)."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from titan_db.models.realtime import LlmCall
from titan_models.types import ChatResult


def make_llm_call_logger(
    session_factory: async_sessionmaker[AsyncSession],
) -> Any:
    async def log_call(payload: dict[str, Any]) -> None:
        result: ChatResult = payload["result"]
        prompt_hash = None
        if result.prompt_tokens:
            prompt_hash = hashlib.sha256(result.model.encode()).hexdigest()[:64]
        row = LlmCall(
            id=uuid.uuid4(),
            session_id=payload.get("session_id"),
            agent_instance_id=payload.get("agent_instance_id"),
            provider=result.provider,
            model=result.model,
            model_role=str(payload.get("model_role") or "agent"),
            purpose=str(payload.get("purpose") or "chat"),
            priority=int(payload.get("priority") or 3),
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            ttft_ms=result.ttft_ms,
            latency_ms=result.latency_ms,
            status=result.finish_reason,
            error=None if result.finish_reason != "error" else "provider error",
            prompt_hash=prompt_hash,
        )
        async with session_factory() as session:
            session.add(row)
            await session.commit()

    return log_call

from __future__ import annotations

import asyncio
import time

import pytest

from titan_models.fake import FakeProvider
from titan_models.llm_scheduler import LlmScheduler
from titan_models.types import ChatMessage, GenerationParams


@pytest.mark.asyncio
async def test_p1_preempts_p3_within_100ms() -> None:
    slow_provider = FakeProvider(block_s=0.15)
    fast_provider = FakeProvider(block_s=0.0)
    scheduler = LlmScheduler(concurrency=2)
    await scheduler.start()
    params = GenerationParams(max_tokens=16)
    slow = asyncio.create_task(
        scheduler.submit(
            priority=3,
            provider=slow_provider,
            model="fake:small",
            messages=[ChatMessage(role="user", content="slow")],
            params=params,
            purpose="deliberation",
            model_role="agent",
        )
    )
    await asyncio.sleep(0.02)
    started = time.monotonic()
    fast = asyncio.create_task(
        scheduler.submit(
            priority=1,
            provider=fast_provider,
            model="fake:small",
            messages=[ChatMessage(role="user", content="fast")],
            params=params,
            purpose="commentary",
            model_role="commentary",
        )
    )
    fast_result = await fast
    slow_result = await slow
    elapsed_ms = (time.monotonic() - started) * 1000
    assert fast_result.finish_reason == "stop"
    assert slow_result.finish_reason == "cancelled"
    assert elapsed_ms < 100
    await scheduler.stop()

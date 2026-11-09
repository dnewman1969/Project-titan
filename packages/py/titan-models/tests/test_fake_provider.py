from __future__ import annotations

import pytest

from titan_models.fake import FakeProvider
from titan_models.types import ChatMessage, GenerationParams


@pytest.mark.asyncio
async def test_fake_provider_scripted_chat() -> None:
    provider = FakeProvider(script=["scripted reply"])
    result = await provider.chat(
        "fake:small",
        [ChatMessage(role="user", content="?")],
        GenerationParams(max_tokens=32),
    )
    assert result.text == "scripted reply"
    assert result.provider == "fake"


@pytest.mark.asyncio
async def test_fake_embedder_unit() -> None:
    from titan_models.embedder import FakeEmbedder

    embedder = FakeEmbedder()
    assert embedder.embed(["abc"])[0][0] == 3.0

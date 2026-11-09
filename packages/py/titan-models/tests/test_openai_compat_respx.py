from __future__ import annotations

import httpx
import pytest
import respx

from titan_models.openai_compat import OpenAICompatProvider
from titan_models.types import ChatMessage, GenerationParams


@pytest.mark.asyncio
@respx.mock
async def test_openai_compat_chat_shape() -> None:
    route = respx.post("http://127.0.0.1:8080/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 4, "completion_tokens": 1},
            },
        )
    )
    provider = OpenAICompatProvider("openai_compat:test", "http://127.0.0.1:8080")
    result = await provider.chat(
        "gpt-test",
        [ChatMessage(role="user", content="hi")],
        GenerationParams(max_tokens=16),
    )
    assert route.called
    assert result.text == "ok"
    assert result.prompt_tokens == 4
    assert result.provider == "openai_compat:test"


@pytest.mark.asyncio
@respx.mock
async def test_openai_compat_list_models() -> None:
    respx.get("http://127.0.0.1:8080/v1/models").mock(
        return_value=httpx.Response(200, json={"data": [{"id": "gpt-test"}]})
    )
    provider = OpenAICompatProvider("openai_compat:test", "http://127.0.0.1:8080")
    assert await provider.list_models() == ["gpt-test"]

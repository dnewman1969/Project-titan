from __future__ import annotations

import httpx
import pytest
import respx

from titan_models.ollama import OllamaProvider
from titan_models.types import ChatMessage, GenerationParams


@pytest.mark.asyncio
@respx.mock
async def test_ollama_chat_shape() -> None:
    route = respx.post("http://127.0.0.1:11434/api/chat").mock(
        return_value=httpx.Response(
            200,
            json={
                "message": {"role": "assistant", "content": "hello"},
                "done": True,
                "prompt_eval_count": 3,
                "eval_count": 2,
            },
        )
    )
    provider = OllamaProvider()
    result = await provider.chat(
        "qwen3:8b",
        [ChatMessage(role="user", content="hi")],
        GenerationParams(max_tokens=32),
    )
    assert route.called
    assert result.text == "hello"
    assert result.prompt_tokens == 3
    assert result.provider == "ollama"


@pytest.mark.asyncio
@respx.mock
async def test_ollama_list_models_shape() -> None:
    respx.get("http://127.0.0.1:11434/api/tags").mock(
        return_value=httpx.Response(200, json={"models": [{"name": "qwen3:8b", "size": 5200000000}]})
    )
    provider = OllamaProvider()
    assert await provider.list_models() == ["qwen3:8b"]

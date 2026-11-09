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


@pytest.mark.asyncio
@respx.mock
async def test_ollama_health_and_embed() -> None:
    respx.get("http://127.0.0.1:11434/api/version").mock(return_value=httpx.Response(200, json={"version": "0.12.0"}))
    respx.post("http://127.0.0.1:11434/api/embed").mock(
        return_value=httpx.Response(200, json={"embeddings": [[0.1, 0.2]]})
    )
    provider = OllamaProvider()
    assert await provider.health() is True
    vectors = await provider.embed("nomic", ["hello"])
    assert vectors == [[0.1, 0.2]]


@pytest.mark.asyncio
@respx.mock
async def test_ollama_stream_chat_final_chunk() -> None:
    chunks = [
        b'{"message":{"content":"hel"},"done":false}\n',
        b'{"message":{"content":"lo"},"done":true,"prompt_eval_count":1,"eval_count":2}\n',
    ]

    def stream(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"".join(chunks))

    respx.post("http://127.0.0.1:11434/api/chat").mock(side_effect=stream)
    provider = OllamaProvider()
    parts: list[str] = []
    final = None
    async for piece in provider.stream_chat(
        "qwen3:8b",
        [ChatMessage(role="user", content="hi")],
        GenerationParams(max_tokens=8),
    ):
        if isinstance(piece, str):
            parts.append(piece)
        else:
            final = piece
    assert "".join(parts) == "hello"
    assert final is not None
    assert final.text == "hello"

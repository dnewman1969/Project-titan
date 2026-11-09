"""Ollama `ModelProvider` (Section 2.9.1)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from collections.abc import AsyncIterator
from typing import Any, Literal

from titan_core.http import HTTPError, local_client
from titan_models.types import ChatMessage, ChatResult, GenerationParams, ModelCapabilities


def _messages_payload(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for msg in messages:
        row: dict[str, Any] = {"role": msg.role, "content": msg.content}
        if msg.name is not None:
            row["name"] = msg.name
        if msg.tool_call_id is not None:
            row["tool_call_id"] = msg.tool_call_id
        out.append(row)
    return out


class OllamaProvider:
    id = "ollama"

    def __init__(self, base_url: str = "http://127.0.0.1:11434", *, timeout_s: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    async def list_models(self) -> list[str]:
        async with local_client(timeout_s=10.0) as client:
            response = await client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
        body = response.json()
        models = body.get("models") if isinstance(body, dict) else None
        if not isinstance(models, list):
            return []
        names: list[str] = []
        for item in models:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                names.append(item["name"])
        return names

    async def list_models_detail(self) -> list[dict[str, Any]]:
        async with local_client(timeout_s=10.0) as client:
            response = await client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
        body = response.json()
        models = body.get("models") if isinstance(body, dict) else None
        if not isinstance(models, list):
            return []
        return [m for m in models if isinstance(m, dict)]

    async def loaded_models(self) -> set[str]:
        async with local_client(timeout_s=10.0) as client:
            response = await client.get(f"{self.base_url}/api/ps")
            if response.status_code != 200:
                return set()
            body = response.json()
        models = body.get("models") if isinstance(body, dict) else None
        if not isinstance(models, list):
            return set()
        return {str(m["name"]) for m in models if isinstance(m, dict) and m.get("name")}

    async def capabilities(self, model: str) -> ModelCapabilities:
        return ModelCapabilities(
            context_tokens=8192,
            supports_tools=True,
            supports_json_schema=True,
            supports_vision=False,
            est_vram_mb=5200,
            device="gpu",
        )

    def _options(self, params: GenerationParams) -> dict[str, Any]:
        options: dict[str, Any] = {
            "temperature": params.temperature,
            "top_p": params.top_p,
            "num_predict": params.max_tokens,
        }
        if params.seed is not None:
            options["seed"] = params.seed
        if params.stop:
            options["stop"] = params.stop
        return options

    def _chat_body(
        self, model: str, messages: list[ChatMessage], params: GenerationParams, *, stream: bool
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": model,
            "messages": _messages_payload(messages),
            "stream": stream,
            "options": self._options(params),
        }
        if params.json_schema is not None:
            body["format"] = params.json_schema
        if params.keep_alive is not None:
            body["keep_alive"] = params.keep_alive
        return body

    async def chat(
        self,
        model: str,
        messages: list[ChatMessage],
        params: GenerationParams,
        cancel: asyncio.Event | None = None,
    ) -> ChatResult:
        started = time.monotonic()
        ttft_ms = 0
        async with local_client(timeout_s=self.timeout_s) as client:
            response = await client.post(
                f"{self.base_url}/api/chat",
                json=self._chat_body(model, messages, params, stream=False),
            )
            if cancel is not None and cancel.is_set():
                return _cancelled(self.id, model)
            response.raise_for_status()
            body = response.json()
        ttft_ms = int((time.monotonic() - started) * 1000)
        latency_ms = ttft_ms
        message = body.get("message") if isinstance(body, dict) else None
        text = ""
        tool_calls: list[dict[str, Any]] = []
        if isinstance(message, dict):
            text = str(message.get("content") or "")
            raw_tools = message.get("tool_calls")
            if isinstance(raw_tools, list):
                tool_calls = [t for t in raw_tools if isinstance(t, dict)]
        prompt_tokens = int((body.get("prompt_eval_count") if isinstance(body, dict) else 0) or 0)
        completion_tokens = int((body.get("eval_count") if isinstance(body, dict) else 0) or 0)
        finish: Literal["stop", "length", "tool", "error", "cancelled"] = "tool" if tool_calls else "stop"
        if isinstance(body, dict) and body.get("done_reason") == "length":
            finish = "length"
        return ChatResult(
            text=text,
            tool_calls=tool_calls,
            model=model,
            provider=self.id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            ttft_ms=ttft_ms,
            latency_ms=latency_ms,
            finish_reason=finish,
        )

    async def stream_chat(
        self,
        model: str,
        messages: list[ChatMessage],
        params: GenerationParams,
        cancel: asyncio.Event | None = None,
    ) -> AsyncIterator[str | ChatResult]:
        started = time.monotonic()
        ttft_ms = 0
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        prompt_tokens = 0
        completion_tokens = 0
        finish: Literal["stop", "length", "tool", "error", "cancelled"] = "stop"
        try:
            async with (
                local_client(timeout_s=self.timeout_s) as client,
                client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json=self._chat_body(model, messages, params, stream=True),
                ) as response,
            ):
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if cancel is not None and cancel.is_set():
                        yield _cancelled(self.id, model)
                        return
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if ttft_ms == 0:
                        message = chunk.get("message") if isinstance(chunk, dict) else None
                        if isinstance(message, dict) and message.get("content"):
                            ttft_ms = int((time.monotonic() - started) * 1000)
                    if isinstance(chunk, dict):
                        message = chunk.get("message")
                        if isinstance(message, dict):
                            delta = message.get("content")
                            if isinstance(delta, str) and delta:
                                text_parts.append(delta)
                                yield delta
                            raw_tools = message.get("tool_calls")
                            if isinstance(raw_tools, list):
                                tool_calls.extend(t for t in raw_tools if isinstance(t, dict))
                        prompt_tokens = int(chunk.get("prompt_eval_count") or prompt_tokens)
                        completion_tokens = int(chunk.get("eval_count") or completion_tokens)
                        if chunk.get("done"):
                            if chunk.get("done_reason") == "length":
                                finish = "length"
                            elif tool_calls:
                                finish = "tool"
                            break
        except HTTPError:
            yield ChatResult(
                text="",
                tool_calls=[],
                model=model,
                provider=self.id,
                prompt_tokens=0,
                completion_tokens=0,
                ttft_ms=0,
                latency_ms=int((time.monotonic() - started) * 1000),
                finish_reason="error",
            )
            return
        latency_ms = int((time.monotonic() - started) * 1000)
        yield ChatResult(
            text="".join(text_parts),
            tool_calls=tool_calls,
            model=model,
            provider=self.id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            ttft_ms=ttft_ms,
            latency_ms=latency_ms,
            finish_reason=finish,
        )

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        async with local_client(timeout_s=self.timeout_s) as client:
            response = await client.post(
                f"{self.base_url}/api/embed",
                json={"model": model, "input": texts},
            )
            response.raise_for_status()
            body = response.json()
        embeddings = body.get("embeddings") if isinstance(body, dict) else None
        if not isinstance(embeddings, list):
            return []
        return [[float(x) for x in row] for row in embeddings if isinstance(row, list)]

    async def ensure_loaded(self, model: str) -> None:
        params = GenerationParams(max_tokens=1, temperature=0.0, keep_alive="5m")
        await self.chat(model, [ChatMessage(role="user", content=".")], params)

    async def unload(self, model: str) -> None:
        async with local_client(timeout_s=30.0) as client:
            await client.post(
                f"{self.base_url}/api/generate",
                json={"model": model, "prompt": "", "keep_alive": 0},
            )

    async def health(self) -> bool:
        try:
            async with local_client(timeout_s=2.0) as client:
                response = await client.get(f"{self.base_url}/api/version")
            return response.status_code == 200
        except HTTPError:
            return False

    async def pull(self, model: str) -> None:
        async with (
            local_client(timeout_s=self.timeout_s) as client,
            client.stream(
                "POST",
                f"{self.base_url}/api/pull",
                json={"name": model, "stream": True},
            ) as response,
        ):
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                with contextlib.suppress(json.JSONDecodeError):
                    json.loads(line)


def _cancelled(provider: str, model: str) -> ChatResult:
    return ChatResult(
        text="",
        tool_calls=[],
        model=model,
        provider=provider,
        prompt_tokens=0,
        completion_tokens=0,
        ttft_ms=0,
        latency_ms=0,
        finish_reason="cancelled",
    )

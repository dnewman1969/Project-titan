"""OpenAI-compatible chat-completions provider (Section 2.9.1)."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Any

from titan_core.http import HTTPError, local_client
from titan_models.ollama import _cancelled
from titan_models.types import ChatMessage, ChatResult, GenerationParams, ModelCapabilities


class OpenAICompatProvider:
    def __init__(self, provider_id: str, base_url: str, *, timeout_s: float = 120.0) -> None:
        self.id = provider_id
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    async def list_models(self) -> list[str]:
        async with local_client(timeout_s=10.0) as client:
            response = await client.get(f"{self.base_url}/v1/models")
            if response.status_code != 200:
                return []
            body = response.json()
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            return []
        return [str(row["id"]) for row in data if isinstance(row, dict) and row.get("id")]

    async def capabilities(self, model: str) -> ModelCapabilities:
        return ModelCapabilities(
            context_tokens=8192,
            supports_tools=True,
            supports_json_schema=False,
            supports_vision=False,
            est_vram_mb=4096,
            device="gpu",
        )

    def _messages(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        return [{"role": m.role, "content": m.content} for m in messages]

    def _body(
        self, model: str, messages: list[ChatMessage], params: GenerationParams, *, stream: bool
    ) -> dict:
        body: dict[str, Any] = {
            "model": model,
            "messages": self._messages(messages),
            "temperature": params.temperature,
            "top_p": params.top_p,
            "max_tokens": params.max_tokens,
            "stream": stream,
        }
        if params.stop:
            body["stop"] = params.stop
        if params.seed is not None:
            body["seed"] = params.seed
        return body

    async def chat(
        self,
        model: str,
        messages: list[ChatMessage],
        params: GenerationParams,
        cancel: asyncio.Event | None = None,
    ) -> ChatResult:
        started = time.monotonic()
        async with local_client(timeout_s=self.timeout_s) as client:
            response = await client.post(
                f"{self.base_url}/v1/chat/completions",
                json=self._body(model, messages, params, stream=False),
            )
            if cancel is not None and cancel.is_set():
                return _cancelled(self.id, model)
            response.raise_for_status()
            body = response.json()
        latency_ms = int((time.monotonic() - started) * 1000)
        choices = body.get("choices") if isinstance(body, dict) else None
        text = ""
        finish = "stop"
        tool_calls: list[dict] = []
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(message, dict):
                text = str(message.get("content") or "")
                raw_tools = message.get("tool_calls")
                if isinstance(raw_tools, list):
                    tool_calls = [t for t in raw_tools if isinstance(t, dict)]
            reason = choices[0].get("finish_reason") if isinstance(choices[0], dict) else None
            if reason == "length":
                finish = "length"
            elif reason == "tool_calls" or tool_calls:
                finish = "tool"
        usage = body.get("usage") if isinstance(body, dict) else {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0) if isinstance(usage, dict) else 0
        completion_tokens = int(usage.get("completion_tokens") or 0) if isinstance(usage, dict) else 0
        return ChatResult(
            text=text,
            tool_calls=tool_calls,
            model=model,
            provider=self.id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            ttft_ms=latency_ms,
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
        parts: list[str] = []
        try:
            async with (
                local_client(timeout_s=self.timeout_s) as client,
                client.stream(
                    "POST",
                    f"{self.base_url}/v1/chat/completions",
                    json=self._body(model, messages, params, stream=True),
                ) as response,
            ):
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if cancel is not None and cancel.is_set():
                        yield _cancelled(self.id, model)
                        return
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") if isinstance(chunk, dict) else None
                    if not isinstance(choices, list) or not choices:
                        continue
                    delta = choices[0].get("delta") if isinstance(choices[0], dict) else None
                    if isinstance(delta, dict):
                        content = delta.get("content")
                        if isinstance(content, str) and content:
                            if ttft_ms == 0:
                                ttft_ms = int((time.monotonic() - started) * 1000)
                            parts.append(content)
                            yield content
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
            text="".join(parts),
            tool_calls=[],
            model=model,
            provider=self.id,
            prompt_tokens=0,
            completion_tokens=0,
            ttft_ms=ttft_ms,
            latency_ms=latency_ms,
            finish_reason="stop",
        )

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError("OpenAI-compatible provider does not implement embed in M3")

    async def ensure_loaded(self, model: str) -> None:
        return None

    async def unload(self, model: str) -> None:
        return None

    async def health(self) -> bool:
        try:
            async with local_client(timeout_s=2.0) as client:
                response = await client.get(f"{self.base_url}/v1/models")
            return response.status_code == 200
        except HTTPError:
            return False

    async def pull(self, model: str) -> None:
        raise NotImplementedError("pull is provider-specific")

"""Deterministic provider for tests (Section 2.9.1)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Literal

from titan_models.types import ChatMessage, ChatResult, GenerationParams, ModelCapabilities

ScriptStep = str | Callable[[], str] | tuple[str, float]


@dataclass
class FakeProvider:
    id: str = "fake"
    models: list[str] = field(default_factory=lambda: ["fake:small", "fake:large"])
    script: list[ScriptStep] = field(default_factory=list)
    block_s: float = 0.0
    _inflight: dict[str, asyncio.Task[None]] = field(default_factory=dict, repr=False)

    async def list_models(self) -> list[str]:
        return list(self.models)

    async def capabilities(self, model: str) -> ModelCapabilities:
        return ModelCapabilities(
            context_tokens=4096,
            supports_tools=False,
            supports_json_schema=True,
            supports_vision=False,
            est_vram_mb=128,
            device="cpu",
        )

    async def _run_script(
        self, model: str, cancel: asyncio.Event | None, hold_s: float
    ) -> tuple[str, int, int]:
        started = time.monotonic()
        if hold_s > 0:
            deadline = started + hold_s
            while time.monotonic() < deadline:
                if cancel is not None and cancel.is_set():
                    return "", 0, int((time.monotonic() - started) * 1000)
                await asyncio.sleep(0.005)
        elif self.block_s > 0:
            deadline = started + self.block_s
            while time.monotonic() < deadline:
                if cancel is not None and cancel.is_set():
                    return "", 0, int((time.monotonic() - started) * 1000)
                await asyncio.sleep(0.005)
        step = self.script.pop(0) if self.script else "ok"
        if callable(step):
            text = step()
        elif isinstance(step, tuple):
            text, delay = step
            await asyncio.sleep(delay)
            if cancel is not None and cancel.is_set():
                return "", 0, int((time.monotonic() - started) * 1000)
        else:
            text = step
        latency = int((time.monotonic() - started) * 1000)
        return text, 5, latency

    async def chat(
        self,
        model: str,
        messages: list[ChatMessage],
        params: GenerationParams,
        cancel: asyncio.Event | None = None,
        *,
        hold_s: float = 0.0,
    ) -> ChatResult:
        text, prompt_tokens, latency_ms = await self._run_script(model, cancel, hold_s)
        finish: Literal["stop", "length", "tool", "error", "cancelled"] = (
            "cancelled" if cancel is not None and cancel.is_set() else "stop"
        )
        return ChatResult(
            text=text,
            tool_calls=[],
            model=model,
            provider=self.id,
            prompt_tokens=prompt_tokens,
            completion_tokens=len(text.split()),
            ttft_ms=min(10, latency_ms),
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
        result = await self.chat(model, messages, params, cancel)
        if result.finish_reason != "cancelled":
            for word in result.text.split():
                if cancel is not None and cancel.is_set():
                    yield ChatResult(
                        text="",
                        tool_calls=[],
                        model=model,
                        provider=self.id,
                        prompt_tokens=0,
                        completion_tokens=0,
                        ttft_ms=0,
                        latency_ms=0,
                        finish_reason="cancelled",
                    )
                    return
                yield word + " "
                await asyncio.sleep(0)
        yield result

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        return [[float(len(t)), 0.1, 0.2] for t in texts]

    async def ensure_loaded(self, model: str) -> None:
        return None

    async def unload(self, model: str) -> None:
        return None

    async def health(self) -> bool:
        return True

    async def pull(self, model: str) -> None:
        await asyncio.sleep(0.05)

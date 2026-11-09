"""`ModelProvider` protocol (Section 2.9.1)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Protocol

from titan_models.types import ChatMessage, ChatResult, GenerationParams, ModelCapabilities


class ModelProvider(Protocol):
    id: str

    async def list_models(self) -> list[str]: ...

    async def capabilities(self, model: str) -> ModelCapabilities: ...

    async def chat(
        self,
        model: str,
        messages: list[ChatMessage],
        params: GenerationParams,
        cancel: asyncio.Event | None = None,
    ) -> ChatResult: ...

    def stream_chat(
        self,
        model: str,
        messages: list[ChatMessage],
        params: GenerationParams,
        cancel: asyncio.Event | None = None,
    ) -> AsyncIterator[str | ChatResult]: ...

    async def embed(self, model: str, texts: list[str]) -> list[list[float]]: ...

    async def ensure_loaded(self, model: str) -> None: ...

    async def unload(self, model: str) -> None: ...

    async def health(self) -> bool: ...

    async def pull(self, model: str) -> None: ...

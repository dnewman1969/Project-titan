"""Agent tool registry (M6.T3)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

ToolHandler = Callable[..., Awaitable[Any]]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolHandler] = {}

    def register(self, name: str, handler: ToolHandler) -> None:
        self._tools[name] = handler

    def names(self) -> list[str]:
        return sorted(self._tools)

    async def call(self, name: str, **kwargs: Any) -> Any:
        if name not in self._tools:
            msg = f"unknown tool {name!r}"
            raise KeyError(msg)
        return await self._tools[name](**kwargs)


def core_tools() -> ToolRegistry:
    registry = ToolRegistry()

    async def bb_read(**_kwargs: Any) -> dict[str, Any]:
        return {"status": "stub"}

    async def bb_write(**_kwargs: Any) -> dict[str, Any]:
        return {"status": "stub"}

    async def memory_search(**_kwargs: Any) -> list[dict[str, Any]]:
        return []

    async def knowledge_search(**_kwargs: Any) -> list[dict[str, Any]]:
        return []

    registry.register("bb.read", bb_read)
    registry.register("bb.write", bb_write)
    registry.register("memory.search", memory_search)
    registry.register("knowledge.search", knowledge_search)
    return registry

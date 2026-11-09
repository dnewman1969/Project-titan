"""Priority LLM scheduler (Section 2.9.3)."""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from titan_models.protocol import ModelProvider
from titan_models.types import ChatMessage, ChatResult, GenerationParams

Priority = int  # P0=0 .. P4=4

P1_STALE_S = 3.0
P3_THROTTLE_SLEEP_S = 0.05


@dataclass
class LlmWorkItem:
    priority: Priority
    provider: ModelProvider
    model: str
    messages: list[ChatMessage]
    params: GenerationParams
    purpose: str
    model_role: str
    session_id: uuid.UUID | None = None
    agent_instance_id: uuid.UUID | None = None
    enqueued_at: float = field(default_factory=time.monotonic)
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    future: asyncio.Future[ChatResult] | None = None


LogFn = Callable[[dict[str, Any]], Awaitable[None]]


class LlmScheduler:
    """Serializes model calls with priority, reserved slots, pre-emption and token budgets."""

    def __init__(
        self,
        *,
        concurrency: int = 2,
        session_live: bool = False,
        max_tokens_per_minute: int = 12_000,
        log_call: LogFn | None = None,
    ) -> None:
        self.concurrency = max(1, concurrency)
        self.session_live = session_live
        self.max_tokens_per_minute = max_tokens_per_minute
        self.log_call = log_call
        self._queue: list[LlmWorkItem] = []
        self._active: list[LlmWorkItem] = []
        self._tokens_window: list[tuple[float, int]] = []
        self._condition = asyncio.Condition()
        self._workers: list[asyncio.Task[None]] = []
        self._stopped = asyncio.Event()

    async def start(self) -> None:
        if self._workers:
            return
        for index in range(self.concurrency):
            self._workers.append(asyncio.create_task(self._worker(index), name=f"llm-worker-{index}"))

    async def stop(self) -> None:
        self._stopped.set()
        for task in self._workers:
            task.cancel()
        for task in self._workers:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._workers.clear()
        for item in self._queue:
            if item.future is not None and not item.future.done():
                item.future.set_result(_cancelled(item))
        for item in self._active:
            item.cancel.set()
            if item.future is not None and not item.future.done():
                item.future.set_result(_cancelled(item))

    def set_session_live(self, live: bool) -> None:
        self.session_live = live

    @property
    def queue_depth(self) -> int:
        return len(self._queue) + len(self._active)

    async def submit(
        self,
        *,
        priority: Priority,
        provider: ModelProvider,
        model: str,
        messages: list[ChatMessage],
        params: GenerationParams,
        purpose: str,
        model_role: str,
        session_id: uuid.UUID | None = None,
        agent_instance_id: uuid.UUID | None = None,
    ) -> ChatResult:
        loop = asyncio.get_running_loop()
        item = LlmWorkItem(
            priority=priority,
            provider=provider,
            model=model,
            messages=messages,
            params=params,
            purpose=purpose,
            model_role=model_role,
            session_id=session_id,
            agent_instance_id=agent_instance_id,
            future=loop.create_future(),
        )
        async with self._condition:
            self._queue.append(item)
            self._queue.sort(key=lambda w: (w.priority, w.enqueued_at))
            self._maybe_preempt(priority)
            self._condition.notify_all()
        assert item.future is not None  # noqa: S101
        return await item.future

    def _maybe_preempt(self, incoming_priority: Priority) -> None:
        if incoming_priority > 1:
            return
        victims = [item for item in self._active if item.priority >= 3]
        if not victims:
            return
        victims.sort(key=lambda w: w.enqueued_at)
        for victim in victims:
            victim.cancel.set()

    def _reserved_slots_in_use(self) -> int:
        if not self.session_live:
            return 0
        return sum(1 for item in self._active if item.priority <= 1)

    def _can_start(self, item: LlmWorkItem) -> bool:
        if len(self._active) >= self.concurrency:
            return False
        if self.session_live and item.priority >= 2 and self._reserved_slots_in_use() >= self.concurrency - 1:
            higher_waiting = any(w.priority <= 1 for w in self._queue)
            if higher_waiting:
                return False
        if item.priority == 1 and time.monotonic() - item.enqueued_at > P1_STALE_S:
            return False
        return not (item.priority >= 3 and self._over_token_budget())

    def _over_token_budget(self) -> bool:
        now = time.monotonic()
        self._tokens_window = [(ts, n) for ts, n in self._tokens_window if now - ts < 60.0]
        used = sum(n for _, n in self._tokens_window)
        return used >= self.max_tokens_per_minute

    async def _worker(self, _index: int) -> None:
        while not self._stopped.is_set():
            item: LlmWorkItem | None = None
            async with self._condition:
                while not self._stopped.is_set():
                    for candidate in sorted(self._queue, key=lambda w: (w.priority, w.enqueued_at)):
                        if self._can_start(candidate):
                            self._queue.remove(candidate)
                            item = candidate
                            self._active.append(candidate)
                            break
                    if item is not None:
                        break
                    if item is None and any(
                        time.monotonic() - w.enqueued_at > P1_STALE_S and w.priority == 1 for w in self._queue
                    ):
                        stale = [
                            w
                            for w in self._queue
                            if w.priority == 1 and time.monotonic() - w.enqueued_at > P1_STALE_S
                        ]
                        for w in stale:
                            self._queue.remove(w)
                            if w.future is not None and not w.future.done():
                                w.future.set_result(_cancelled(w))
                        continue
                    p3_throttled = any(w.priority >= 3 for w in self._queue) and self._over_token_budget()
                    if item is None and p3_throttled:
                        await asyncio.sleep(P3_THROTTLE_SLEEP_S)
                        continue
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(self._condition.wait(), timeout=0.05)
                if item is None and self._stopped.is_set():
                    return
            if item is None:
                continue
            if item.priority == 1 and time.monotonic() - item.enqueued_at > P1_STALE_S:
                self._active.remove(item)
                if item.future is not None and not item.future.done():
                    item.future.set_result(_cancelled(item))
                async with self._condition:
                    self._condition.notify_all()
                continue
            try:
                if item.cancel.is_set():
                    result = _cancelled(item)
                else:
                    result = await item.provider.chat(
                        item.model, item.messages, item.params, cancel=item.cancel
                    )
            except Exception:
                result = ChatResult(
                    text="",
                    tool_calls=[],
                    model=item.model,
                    provider=item.provider.id,
                    prompt_tokens=0,
                    completion_tokens=0,
                    ttft_ms=0,
                    latency_ms=0,
                    finish_reason="error",
                )
            finally:
                with contextlib.suppress(ValueError):
                    self._active.remove(item)
            self._record_tokens(result)
            if item.future is not None and not item.future.done():
                item.future.set_result(result)
            if self.log_call is not None:
                await self.log_call(
                    {
                        "session_id": item.session_id,
                        "agent_instance_id": item.agent_instance_id,
                        "provider": item.provider.id,
                        "model": item.model,
                        "model_role": item.model_role,
                        "purpose": item.purpose,
                        "priority": item.priority,
                        "result": result,
                    }
                )
            async with self._condition:
                self._condition.notify_all()

    def _record_tokens(self, result: ChatResult) -> None:
        total = result.prompt_tokens + result.completion_tokens
        if total > 0:
            self._tokens_window.append((time.monotonic(), total))


def _cancelled(item: LlmWorkItem) -> ChatResult:
    return ChatResult(
        text="",
        tool_calls=[],
        model=item.model,
        provider=item.provider.id,
        prompt_tokens=0,
        completion_tokens=0,
        ttft_ms=0,
        latency_ms=0,
        finish_reason="cancelled",
    )

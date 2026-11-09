"""Background pull jobs for `/models/pull`."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal

import redis.asyncio as aioredis

from titan_core.protocol.ws import JobUpdateData
from titan_models.registry import ModelsRegistry

JOB_STREAM = "titan:jobs"
ProgressFn = Callable[[JobUpdateData], Awaitable[None]]


@dataclass
class PullJobRunner:
    registry: ModelsRegistry
    redis: aioredis.Redis | None = None
    on_progress: ProgressFn | None = None
    _tasks: dict[uuid.UUID, asyncio.Task[None]] = field(default_factory=dict)

    async def start_pull(self, provider_id: str, model: str) -> uuid.UUID:
        job_id = uuid.uuid4()
        task = asyncio.create_task(self._run_pull(job_id, provider_id, model), name=f"pull-{job_id}")
        self._tasks[job_id] = task
        return job_id

    async def _run_pull(self, job_id: uuid.UUID, provider_id: str, model: str) -> None:
        state: Literal["queued", "running", "succeeded", "failed"] = "running"
        await self._publish(job_id, "models.pull", state, 0.0)
        try:
            provider = self.registry.provider_for(provider_id)
            await provider.pull(model)
        except Exception as exc:
            await self._publish(job_id, "models.pull", "failed", 1.0, error=type(exc).__name__)
        else:
            await self._publish(job_id, "models.pull", "succeeded", 1.0)
        finally:
            self._tasks.pop(job_id, None)

    async def _publish(
        self,
        job_id: uuid.UUID,
        kind: str,
        state: Literal["queued", "running", "succeeded", "failed", "cancelled"],
        progress: float,
        *,
        error: str | None = None,
    ) -> None:
        update = JobUpdateData(id=job_id, kind=kind, state=state, progress=progress, error=error)
        if self.on_progress is not None:
            await self.on_progress(update)
        if self.redis is not None:
            await self.redis.xadd(
                JOB_STREAM,
                {"data": update.model_dump_json()},
                maxlen=1000,
                approximate=True,
            )

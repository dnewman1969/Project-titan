"""Redis keys (Section 2.5) and the client factory every process uses.

Stream entries carry one field, `data`, holding the JSON of a protocol model.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import redis.asyncio as aioredis
from pydantic import BaseModel

from titan_core.config import RedisConfig
from titan_core.secrets import resolve_secret

SESSION_STREAM_PREFIX = "titan:s:"
PERSIST_GROUP = "persist"
PERSIST_CONSUMER = "api"
BUS_TAIL = ":bus"
EVENTS_TAIL = ":events"

SYS_METRICS = "titan:sys:metrics"
SYS_METRICS_MAXLEN = 3600
SAFETY_STATE = "titan:safety:state"
SAFETY_KILL = "titan:safety:kill"
DATA_FIELD = "data"
REDIS_PROTOCOL = 2
"""RESP2, pinned: redis-py 8 defaults to RESP3, whose `HELLO` older Redis-compatible servers reject
and whose replies (`XREAD` as a dict) differ from the shapes this codebase parses."""


def redis_client(cfg: RedisConfig, *, timeout_s: float = 2.0) -> aioredis.Redis:
    """A client for `cfg.url`, authenticating with the configured or keyring password."""
    password = resolve_secret(cfg.password, "redis")
    return aioredis.Redis.from_url(
        cfg.url,
        password=password.get_secret_value() if password else None,
        socket_timeout=timeout_s,
        socket_connect_timeout=timeout_s,
        decode_responses=True,
        health_check_interval=0,
        protocol=REDIS_PROTOCOL,
    )


async def xadd_model(client: aioredis.Redis, stream: str, model: BaseModel, *, maxlen: int) -> str:
    fields = {DATA_FIELD: model.model_dump_json()}
    entry_id = await client.xadd(stream, fields, maxlen=maxlen, approximate=True)  # type: ignore[arg-type]
    return str(entry_id)


def entry_data(fields: Mapping[Any, Any]) -> str:
    value = fields.get(DATA_FIELD)
    if not isinstance(value, str):
        raise ValueError(f"stream entry has no {DATA_FIELD!r} field")
    return value


def session_bus_stream(session_id: str) -> str:
    return f"{SESSION_STREAM_PREFIX}{session_id}{BUS_TAIL}"


def session_events_stream(session_id: str) -> str:
    return f"{SESSION_STREAM_PREFIX}{session_id}{EVENTS_TAIL}"


def parse_session_stream(stream: str, *, tail: str) -> str | None:
    prefix = SESSION_STREAM_PREFIX
    if not stream.startswith(prefix) or not stream.endswith(tail):
        return None
    body = stream[len(prefix) : -len(tail)]
    return body or None


async def latest_entry(client: aioredis.Redis, stream: str) -> tuple[str, str] | None:
    """`(entry id, data json)` of the newest entry, or None when the stream is empty."""
    entries = await client.xrevrange(stream, count=1)
    if not entries:
        return None
    entry_id, fields = entries[0]
    return str(entry_id), entry_data(fields or {})

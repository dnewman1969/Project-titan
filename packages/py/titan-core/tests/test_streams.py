"""Redis stream helpers (Section 2.5) against fakeredis."""

from __future__ import annotations

import fakeredis
import pytest
from pydantic import SecretStr

from titan_core import streams
from titan_core.config import RedisConfig
from titan_core.protocol.system import DependencyState


async def test_xadd_and_latest_entry() -> None:
    client = fakeredis.FakeAsyncRedis(decode_responses=True)
    assert await streams.latest_entry(client, streams.SYS_METRICS) is None
    await streams.xadd_model(client, streams.SYS_METRICS, DependencyState(state="up"), maxlen=10)
    last_id = await streams.xadd_model(
        client, streams.SYS_METRICS, DependencyState(state="down", detail="x"), maxlen=10
    )
    latest = await streams.latest_entry(client, streams.SYS_METRICS)
    assert latest is not None
    entry_id, data = latest
    assert entry_id == last_id
    assert DependencyState.model_validate_json(data) == DependencyState(state="down", detail="x")
    await client.aclose()


def test_entry_data_requires_the_data_field() -> None:
    assert streams.entry_data({"data": "{}"}) == "{}"
    with pytest.raises(ValueError, match="'data'"):
        streams.entry_data({"other": "{}"})


def test_session_stream_names_roundtrip() -> None:
    sid = "01933e7a-0000-7000-8000-000000000001"
    bus = streams.session_bus_stream(sid)
    assert streams.parse_session_stream(bus, tail=":bus") == sid
    events = streams.session_events_stream(sid)
    assert streams.parse_session_stream(events, tail=":events") == sid
    telemetry = streams.session_telemetry_stream(sid)
    assert telemetry == f"titan:s:{sid}:telemetry"


async def test_redis_client_uses_the_configured_password() -> None:
    client = streams.redis_client(RedisConfig(url="redis://127.0.0.1:1/0", password=SecretStr("pw")))
    kwargs = client.connection_pool.connection_kwargs
    assert kwargs["password"] == "pw"
    assert kwargs["port"] == 1
    assert kwargs["protocol"] == 2
    await client.aclose()

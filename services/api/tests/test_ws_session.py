from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import UUID

import fakeredis
import pytest
from fastapi.testclient import TestClient

from titan_api.main import create_app
from titan_core.clock import utc_now
from titan_core.config import TitanConfig
from titan_core.protocol.events import GameEvent
from titan_core.protocol.system import SupervisorStatus
from titan_core.protocol.telemetry import TELEMETRY_SCHEMA, TelemetryFrameUI
from titan_core.streams import DATA_FIELD, session_events_stream, session_telemetry_stream

TOKEN = "test-launch-token"
SID = "0193abcd-1111-4111-8111-111111111111"


async def no_supervisor() -> SupervisorStatus | None:
    return None


@pytest.fixture
def client() -> Iterator[TestClient]:
    server = fakeredis.FakeServer()
    redis = fakeredis.FakeAsyncRedis(server=server, decode_responses=True)
    app = create_app(
        TitanConfig(),
        launch_token=TOKEN,
        checks={},
        supervisor=no_supervisor,
        redis=redis,
        start_persister=False,
        enable_database=False,
    )
    with TestClient(app) as test_client:
        yield test_client


def _auth(conn: Any) -> None:
    conn.send_json({"op": "auth", "token": TOKEN, "client": "test/1.0"})
    assert conn.receive_json()["ok"] is True


def test_session_telemetry_and_events_subscribe(client: TestClient) -> None:
    import asyncio

    async def seed() -> None:
        redis = client.app.state.redis
        frame = TelemetryFrameUI.model_validate(
            {
                "schema": TELEMETRY_SCHEMA,
                "session_id": SID,
                "game": "ksp",
                "adapter_version": "1.0.0",
                "seq": 1,
                "t_mono_ns": 1,
                "t_session_ms": 0,
                "t_game_s": 0,
                "paused": False,
                "scene": "flight",
                "domain": "space",
                "vehicle": {
                    "name": None,
                    "kind": "rocket",
                    "position": None,
                    "geo": None,
                    "attitude": None,
                    "velocity": {"speed_mps": 10, "vertical_mps": None, "horizontal_mps": None},
                    "accel_g": None,
                    "controls": None,
                    "engine": None,
                    "damage": {"overall": None, "parts": {}},
                    "situation": "flying",
                    "stage": None,
                    "orbit": None,
                },
                "resources": [],
                "environment": None,
                "job": None,
                "economy": None,
            }
        )
        await redis.xadd(session_telemetry_stream(SID), {DATA_FIELD: frame.model_dump_json(by_alias=True)})
        event = GameEvent(
            id=UUID(int=1),
            session_id=UUID(SID),
            seq=1,
            type="ksp.launch",
            category="game",
            severity="notice",
            salience=0.5,
            source="rule:ksp.launch",
            t_mono_ns=1,
            t_session_ms=0,
            occurred_at=utc_now(),
            frame_seq=1,
            payload={},
        )
        await redis.xadd(session_events_stream(SID), {DATA_FIELD: event.model_dump_json(by_alias=True)})

    asyncio.run(seed())

    with client.websocket_connect("/api/v1/ws") as conn:
        _auth(conn)
        conn.send_json(
            {"op": "subscribe", "req_id": "t1", "channel": f"session.{SID}.telemetry"},
        )
        assert conn.receive_json() == {"op": "ack", "req_id": "t1", "ok": True, "error": None}
        telemetry = conn.receive_json()
        assert telemetry["type"] == "telemetry.frame"
        conn.send_json({"op": "subscribe", "req_id": "e1", "channel": f"session.{SID}.events"})
        assert conn.receive_json()["ok"] is True
        game_event = conn.receive_json()
        assert game_event["type"] == "game.event"

from __future__ import annotations

import json
import uuid

import pytest
from pydantic import ValidationError

from titan_core.protocol import MESSAGE_TYPES, Address, Envelope, make_envelope, parse_payload
from titan_core.protocol.envelope import MAX_ENVELOPE_BYTES
from titan_core.protocol.payloads import FloorRequest, UnknownMessageType
from titan_core.protocol.ws import WS_MESSAGE_TYPES, ClientFrame, ServerFrame, SubscribeFrame

SID = uuid.UUID("0193f19c-0000-7000-8000-00000000aaaa")
GENE = Address(
    kind="agent", id=str(uuid.uuid4()), role="flight_engineer", persona_slug="ksp.flight_engineer.gene"
)


def test_make_envelope_stamps_ids_and_time() -> None:
    env = make_envelope(
        type="floor.request",
        session_id=SID,
        sender=GENE,
        recipients=["system"],
        visibility="internal",
        priority=5,
        payload=FloorRequest(urgency=0.7, topic="max-Q", est_words=20),
        ttl_ms=2000,
    )
    assert env.id.version == 7
    assert env.schema_ == "titan.msg/1"
    assert env.ts.tzinfo is not None
    assert env.t_mono_ns > 0
    wire = env.to_wire()
    assert wire["schema"] == "titan.msg/1"
    assert "schema_" not in wire
    assert "mission_id" not in wire  # optional fields that were never set are omitted
    assert wire["payload"] == {"urgency": 0.7, "topic": "max-Q", "est_words": 20}
    assert len(json.dumps(wire)) < MAX_ENVELOPE_BYTES
    assert Envelope.model_validate(wire) == env
    assert parse_payload(env) == FloorRequest(urgency=0.7, topic="max-Q", est_words=20)


def test_make_envelope_validates() -> None:
    with pytest.raises(ValidationError):
        make_envelope(
            type="floor.request",
            session_id=SID,
            sender=GENE,
            recipients=["nobody"],
            visibility="internal",
            priority=5,
            payload={},
        )


def test_parse_payload_rejects_unknown_type() -> None:
    env = make_envelope(
        type="custom.thing",
        session_id=SID,
        sender=GENE,
        recipients=["broadcast"],
        visibility="internal",
        priority=1,
        payload={},
    )
    with pytest.raises(UnknownMessageType):
        parse_payload(env)


def test_registry_covers_section_6_2_types() -> None:
    expected = {
        "task.assign", "task.accept", "task.reject", "task.progress", "task.blocked", "task.complete",
        "task.fail", "task.cancel", "task.evaluate", "bb.written", "conflict.raised", "query.ask",
        "query.answer", "chat.say", "chat.delta", "user.say", "floor.request", "floor.grant",
        "floor.deny", "floor.release", "floor.preempt", "agent.spawn", "agent.ready",
        "agent.heartbeat", "agent.terminate", "agent.terminated", "game.event", "world.tick",
        "action.propose", "action.decision", "action.executed", "safety.kill", "safety.override",
        "safety.resume", "mission.update", "director.report",
    }  # fmt: skip
    assert set(MESSAGE_TYPES) == expected


def test_ws_frames_discriminate_on_op() -> None:
    frame = ClientFrame.model_validate({"op": "subscribe", "req_id": "r1", "channel": "system.metrics"})
    assert isinstance(frame.root, SubscribeFrame)
    with pytest.raises(ValidationError):
        ServerFrame.model_validate({"op": "subscribe", "req_id": "r1", "channel": "x"})
    assert "telemetry.frame" in WS_MESSAGE_TYPES

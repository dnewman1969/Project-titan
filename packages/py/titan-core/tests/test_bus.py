from __future__ import annotations

from uuid import UUID

import pytest

from titan_core.bus import EnvelopeValidationError, validate_envelope, validate_envelope_raw
from titan_core.protocol.envelope import Address, make_envelope

SID = UUID("0193f19c-0000-7000-8000-00000000aaaa")


def test_validate_envelope_raw_round_trip() -> None:
    env = make_envelope(
        type="chat.say",
        session_id=SID,
        sender=Address(kind="agent", id="0193f19c-1111-7000-8000-000000000e01", role="pilot"),
        recipients=["broadcast"],
        visibility="public",
        priority=5,
        payload={"text": "hello", "kind": "say"},
    )
    wire = env.model_dump_json(by_alias=True)
    parsed = validate_envelope_raw(wire, session_id=SID)
    assert parsed.id == env.id


def test_validate_envelope_rejects_wrong_session() -> None:
    env = make_envelope(
        type="chat.say",
        session_id=SID,
        sender=Address(kind="system", id="system"),
        recipients=["broadcast"],
        visibility="public",
        priority=5,
        payload={"text": "x", "kind": "say"},
    )
    other = UUID("0193f19c-0001-7000-8000-00000000bbbb")
    with pytest.raises(EnvelopeValidationError):
        validate_envelope_raw(env.model_dump_json(by_alias=True), session_id=other)


def test_validate_envelope_size_limit() -> None:
    env = make_envelope(
        type="chat.say",
        session_id=SID,
        sender=Address(kind="system", id="system"),
        recipients=["broadcast"],
        visibility="public",
        priority=5,
        payload={"text": "x" * 40_000, "kind": "say"},
    )
    with pytest.raises(EnvelopeValidationError):
        validate_envelope(env)

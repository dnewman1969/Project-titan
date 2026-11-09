from __future__ import annotations

from uuid import UUID

from hypothesis import given
from hypothesis import strategies as st

from titan_core.config import FloorConfig
from titan_core.ids import uuid7
from titan_core.protocol.payloads import FloorRequest
from titan_orchestrator.floor import FloorManager

AGENT_A = UUID("0193f19c-1111-7000-8000-000000000e01")
AGENT_B = UUID("0193f19c-2222-7000-8000-000000000e02")


def test_only_one_active_say() -> None:
    floor = FloorManager(FloorConfig())
    assert floor.begin_say(AGENT_A)
    assert not floor.begin_say(AGENT_B)
    floor.end_say(AGENT_A, "first line")
    assert floor.begin_say(AGENT_B)


@given(st.data())
def test_floor_invariant_randomized(data: st.DataObject) -> None:
    floor = FloorManager(FloorConfig(arbitration_ms=0))
    active = 0
    for _ in range(200):
        agent = data.draw(st.sampled_from([AGENT_A, AGENT_B]))
        if data.draw(st.booleans()):
            if floor.begin_say(agent):
                active += 1
                assert active == 1
        else:
            floor.end_say(agent)
            active = 0
    assert active in {0, 1}


def test_floor_request_grant() -> None:
    floor = FloorManager(FloorConfig(arbitration_ms=0))
    req_id = uuid7()
    now = 1_000_000
    floor.request_floor(
        request_id=req_id,
        instance_id=AGENT_A,
        payload=FloorRequest(urgency=0.9, topic="max-q", est_words=12),
        role="flight_engineer",
        now_ms=now,
    )
    grant = floor.grant_if_ready(now_ms=now + 1)
    assert grant is not None
    assert grant.request_id == req_id

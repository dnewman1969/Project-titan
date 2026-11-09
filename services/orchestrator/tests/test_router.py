from __future__ import annotations

import time
from uuid import UUID

from titan_core.protocol.envelope import Address, make_envelope
from titan_orchestrator.router import AgentInbox, AgentRegistration, MessageRouter

SID = UUID("0193f19c-0000-7000-8000-00000000aaaa")
AGENT = UUID("0193f19c-1111-7000-8000-000000000e01")


def _env(type_: str, recipients: list[str], priority: int = 5, ttl_ms: int | None = None):
    return make_envelope(
        type=type_,
        session_id=SID,
        sender=Address(kind="agent", id=str(AGENT), role="flight_engineer"),
        recipients=recipients,
        visibility="internal",
        priority=priority,
        ttl_ms=ttl_ms,
        payload={"text": "hi", "kind": "say"} if type_ == "chat.say" else {"task_id": str(SID)},
    )


def test_router_resolves_role_and_delivers() -> None:
    router = MessageRouter()
    router.register(
        AgentRegistration(instance_id=AGENT, role="flight_engineer", persona_slug="ksp.flight_engineer.gene")
    )
    count = router.deliver(_env("chat.say", ["role:flight_engineer"]))
    assert count == 1
    assert len(router.inbox(AGENT).pop_all()) == 1


def test_inbox_drops_expired_ttl() -> None:
    inbox = AgentInbox()
    env = _env("chat.say", ["broadcast"], ttl_ms=1)
    # TTL is measured from envelope wall time; wait so the message is stale.
    time.sleep(0.05)
    stale_now = int(env.ts.timestamp() * 1000) + 5
    assert inbox.push(env, now_ms=stale_now) is False


def test_inbox_priority_order() -> None:
    inbox = AgentInbox()
    inbox.push(_env("chat.say", ["broadcast"], priority=3))
    inbox.push(_env("chat.say", ["broadcast"], priority=8))
    items = inbox.pop_all()
    assert items[0].priority == 8

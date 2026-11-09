"""In-process envelope router: recipient resolution and priority inboxes (M6.T1)."""

from __future__ import annotations

import fnmatch
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import UUID

from titan_core.bus import envelope_expired
from titan_core.protocol.envelope import Address, Envelope

TASK_TYPES = frozenset(
    {
        "task.assign",
        "task.accept",
        "task.reject",
        "task.progress",
        "task.blocked",
        "task.complete",
        "task.fail",
        "task.cancel",
        "task.evaluate",
    }
)
SAFETY_TYPES = frozenset({"safety.kill", "safety.override", "safety.resume"})


@dataclass(frozen=True, slots=True)
class AgentRegistration:
    instance_id: UUID
    role: str
    persona_slug: str | None = None
    team_slug: str | None = None
    is_director: bool = False
    muted: bool = False


@dataclass(slots=True)
class InboxMessage:
    priority: int
    seq: int
    envelope: Envelope
    enqueued_ms: int


@dataclass
class AgentInbox:
    max_depth: int = 200
    _seq: int = 0
    _items: list[InboxMessage] = field(default_factory=list)

    def depth(self) -> int:
        return len(self._items)

    def push(self, envelope: Envelope, *, now_ms: int | None = None) -> bool:
        if envelope_expired(envelope, now_ms=now_ms):
            return False
        self._seq += 1
        now = int(time.time() * 1000) if now_ms is None else now_ms
        self._items.append(
            InboxMessage(priority=envelope.priority, seq=self._seq, envelope=envelope, enqueued_ms=now)
        )
        self._items.sort(key=lambda item: (-item.priority, item.seq))
        while len(self._items) > self.max_depth:
            self._drop_oldest_non_task()
        return True

    def _drop_oldest_non_task(self) -> None:
        for index, item in enumerate(reversed(self._items)):
            if item.envelope.type not in TASK_TYPES:
                del self._items[len(self._items) - 1 - index]
                return
        self._items.pop(0)

    def pop_all(self) -> list[Envelope]:
        items = [item.envelope for item in self._items]
        self._items.clear()
        return items


SafetyHandler = Callable[[Envelope], None]


class MessageRouter:
    """Resolves recipients and fans out to per-instance inboxes."""

    def __init__(self) -> None:
        self._agents: dict[UUID, AgentRegistration] = {}
        self._inboxes: dict[UUID, AgentInbox] = {}
        self._director_id: UUID | None = None
        self._safety_handler: SafetyHandler | None = None

    def set_safety_handler(self, handler: SafetyHandler | None) -> None:
        self._safety_handler = handler

    def register(self, registration: AgentRegistration) -> None:
        self._agents[registration.instance_id] = registration
        self._inboxes.setdefault(registration.instance_id, AgentInbox())
        if registration.is_director:
            self._director_id = registration.instance_id

    def unregister(self, instance_id: UUID) -> None:
        self._agents.pop(instance_id, None)
        self._inboxes.pop(instance_id, None)
        if self._director_id == instance_id:
            self._director_id = None

    def resolve(self, envelope: Envelope) -> list[UUID]:
        if envelope.type in SAFETY_TYPES:
            return []
        targets: set[UUID] = set()
        for recipient in envelope.recipients:
            if recipient == "broadcast":
                targets.update(self._agents)
            elif recipient == "director" and self._director_id is not None:
                targets.add(self._director_id)
            elif recipient == "system" or recipient == "user":
                continue
            elif recipient.startswith("instance:"):
                raw = recipient.split(":", 1)[1]
                try:
                    targets.add(UUID(raw))
                except ValueError:
                    continue
            elif recipient.startswith("role:"):
                role = recipient.split(":", 1)[1]
                targets.update(iid for iid, reg in self._agents.items() if reg.role == role)
            elif recipient.startswith("persona:"):
                slug = recipient.split(":", 1)[1]
                targets.update(
                    iid
                    for iid, reg in self._agents.items()
                    if reg.persona_slug == slug or slug in (reg.persona_slug or "")
                )
            elif recipient.startswith("team:"):
                team = recipient.split(":", 1)[1]
                targets.update(iid for iid, reg in self._agents.items() if reg.team_slug == team)
        return sorted(targets)

    def deliver(self, envelope: Envelope, *, now_ms: int | None = None) -> int:
        if envelope.type in SAFETY_TYPES and self._safety_handler is not None:
            self._safety_handler(envelope)
            return 0
        delivered = 0
        for instance_id in self.resolve(envelope):
            inbox = self._inboxes.setdefault(instance_id, AgentInbox())
            if inbox.push(envelope, now_ms=now_ms):
                delivered += 1
        return delivered

    def inbox(self, instance_id: UUID) -> AgentInbox:
        return self._inboxes.setdefault(instance_id, AgentInbox())

    def registration(self, instance_id: UUID) -> AgentRegistration | None:
        return self._agents.get(instance_id)


def sender_matches_role(sender: Address, pattern: str) -> bool:
    if pattern.endswith(".*"):
        prefix = pattern[:-2]
        return sender.role == prefix or (sender.role or "").startswith(prefix + ".")
    return fnmatch.fnmatch(sender.role or "", pattern)

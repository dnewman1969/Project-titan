"""Commentary turn-taking (Floor Manager, M6.T5)."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from uuid import UUID

from titan_core.config import FloorConfig
from titan_core.protocol.payloads import ChatSay, FloorDeny, FloorGrant, FloorRequest


@dataclass(slots=True)
class FloorRequestRecord:
    request_id: UUID
    instance_id: UUID
    payload: FloorRequest
    score: float
    received_ms: int


@dataclass
class FloorManager:
    cfg: FloorConfig
    _holder: UUID | None = None
    _active_say: bool = False
    _last_spoke_ms: dict[UUID, int] = field(default_factory=dict)
    _last_utterances: list[str] = field(default_factory=list)
    _pending: list[FloorRequestRecord] = field(default_factory=list)
    _arbitration_deadline_ms: int | None = None

    @property
    def holder(self) -> UUID | None:
        return self._holder

    @property
    def active_say(self) -> bool:
        return self._active_say

    def request_floor(
        self,
        *,
        request_id: UUID,
        instance_id: UUID,
        payload: FloorRequest,
        role: str,
        talkativeness: float = 0.5,
        now_ms: int | None = None,
    ) -> None:
        now = _now_ms(now_ms)
        score = _score(payload, role=role, talkativeness=talkativeness, manager=self, now_ms=now)
        self._pending.append(
            FloorRequestRecord(
                request_id=request_id,
                instance_id=instance_id,
                payload=payload,
                score=score,
                received_ms=now,
            )
        )
        if self._arbitration_deadline_ms is None:
            self._arbitration_deadline_ms = now + self.cfg.arbitration_ms

    def grant_if_ready(self, *, now_ms: int | None = None) -> FloorGrant | None:
        now = _now_ms(now_ms)
        if self._active_say:
            return None
        if not self._pending:
            return None
        if self._arbitration_deadline_ms is not None and now < self._arbitration_deadline_ms:
            return None
        best = max(self._pending, key=lambda item: item.score)
        if best.score < 0.2:
            self._pending.clear()
            self._arbitration_deadline_ms = None
            return None
        self._pending.clear()
        self._arbitration_deadline_ms = None
        self._holder = best.instance_id
        return FloorGrant(
            request_id=best.request_id,
            max_words=self.cfg.max_words,
            deadline_ms=2500,
        )

    def begin_say(self, instance_id: UUID) -> bool:
        """Enforce at most one active `say` stream."""
        if self._active_say:
            return False
        self._active_say = True
        self._holder = instance_id
        return True

    def end_say(self, instance_id: UUID, text: str | None = None) -> None:
        if self._holder == instance_id:
            self._active_say = False
            self._holder = None
            self._last_spoke_ms[instance_id] = _now_ms()
            if text:
                self._last_utterances.append(text)
                self._last_utterances = self._last_utterances[-10:]

    def deny_stale(self, request_id: UUID, *, now_ms: int | None = None) -> FloorDeny:
        del now_ms
        return FloorDeny(request_id=request_id, reason="stale")

    def check_anti_repetition(self, text: str) -> bool:
        if not self._last_utterances:
            return True
        return all(_cosine_similarity(text, prior) <= 0.92 for prior in self._last_utterances)

    def register_utterance(self, payload: ChatSay) -> bool:
        if payload.kind != "say":
            return True
        return self.check_anti_repetition(payload.text)


def _score(
    payload: FloorRequest,
    *,
    role: str,
    talkativeness: float,
    manager: FloorManager,
    now_ms: int,
) -> float:
    del role
    time_since = min(1.0, (now_ms - min(manager._last_spoke_ms.values(), default=now_ms - 60_000)) / 60_000)
    repetition = 0.2 if manager._last_utterances else 0.0
    same_speaker = 0.1 if manager._holder else 0.0
    return (
        0.45 * payload.urgency + 0.15 * time_since + 0.10 * talkativeness - 0.20 * repetition - same_speaker
    )


def _now_ms(now_ms: int | None = None) -> int:
    return int(time.time() * 1000) if now_ms is None else now_ms


def _cosine_similarity(a: str, b: str) -> float:
    tokens_a = a.lower().split()
    tokens_b = b.lower().split()
    if not tokens_a or not tokens_b:
        return 0.0
    set_a = set(tokens_a)
    set_b = set(tokens_b)
    inter = len(set_a & set_b)
    denom = math.sqrt(len(set_a) * len(set_b))
    return inter / denom if denom else 0.0

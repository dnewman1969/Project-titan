"""Retrieval scoring (Section 4.3)."""

from __future__ import annotations

import math
from datetime import UTC, datetime


def retrieval_score(
    similarity: float,
    importance: float,
    confidence: float,
    occurred_at: datetime,
    *,
    now: datetime | None = None,
) -> float:
    reference = now or datetime.now(tz=UTC)
    age_days = max(0.0, (reference - occurred_at).total_seconds() / 86400.0)
    recency = math.exp(-age_days / 30.0)
    return 0.6 * similarity + 0.2 * importance + 0.1 * recency + 0.1 * confidence

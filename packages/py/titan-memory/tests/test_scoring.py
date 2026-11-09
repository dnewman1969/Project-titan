from __future__ import annotations

from datetime import UTC, datetime, timedelta

from titan_memory.scoring import retrieval_score


def test_retrieval_score_weights_recent_higher() -> None:
    now = datetime(2026, 1, 10, tzinfo=UTC)
    recent = retrieval_score(0.9, 0.5, 0.5, now - timedelta(days=1), now=now)
    older = retrieval_score(0.9, 0.5, 0.5, now - timedelta(days=60), now=now)
    assert recent > older

from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from hypothesis import given
from hypothesis import strategies as st

from titan_core import ids


def test_uuid7_version_and_variant() -> None:
    value = ids.uuid7()
    assert value.version == 7
    assert value.variant == uuid.RFC_4122


def test_uuid7_embeds_current_unix_ms() -> None:
    before = time.time_ns() // 1_000_000
    value = ids.uuid7()
    after = time.time_ns() // 1_000_000
    # The counter can borrow at most a few ms when a burst overflows it.
    assert before <= ids.uuid7_unix_ms(value) <= after + 2


def test_uuid7_strictly_increasing_in_burst() -> None:
    values = [ids.uuid7() for _ in range(20_000)]
    assert values == sorted(values)
    assert len(set(values)) == len(values)


def test_uuid7_unique_across_threads() -> None:
    with ThreadPoolExecutor(max_workers=8) as pool:
        batches = list(pool.map(lambda _: [ids.uuid7() for _ in range(2_000)], range(8)))
    flat = [v for batch in batches for v in batch]
    assert len(set(flat)) == len(flat)


def test_uuid7_monotonic_when_clock_steps_back(monkeypatch: pytest.MonkeyPatch) -> None:
    first = ids.uuid7()
    real_ms = ids.uuid7_unix_ms(first)
    monkeypatch.setattr(ids.time, "time_ns", lambda: (real_ms - 5_000) * 1_000_000)
    second = ids.uuid7()
    assert second > first


def test_counter_overflow_rolls_into_next_ms(monkeypatch: pytest.MonkeyPatch) -> None:
    frozen = (ids.uuid7_unix_ms(ids.uuid7()) + 10) * 1_000_000
    monkeypatch.setattr(ids.time, "time_ns", lambda: frozen)
    values = [ids.uuid7() for _ in range(5_000)]
    assert values == sorted(values)
    assert ids.uuid7_unix_ms(values[-1]) > frozen // 1_000_000


def test_uuid7_unix_ms_rejects_other_versions() -> None:
    with pytest.raises(ValueError, match="not a UUIDv7"):
        ids.uuid7_unix_ms(uuid.uuid4())


@given(st.integers(min_value=1, max_value=50))
def test_new_id_is_canonical_string(n: int) -> None:
    for _ in range(n):
        text = ids.new_id()
        assert text == str(uuid.UUID(text))
        assert uuid.UUID(text).version == 7

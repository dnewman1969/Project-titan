"""Play commentary persona hooks."""

from __future__ import annotations

from titan_orchestrator.play_commentary import ROSTER, pick_play_commentary


def test_pick_play_commentary_success_uses_smack_talk() -> None:
    line = pick_play_commentary(ok=True, impressive=True)
    assert line["kind"] == "incredible"
    assert line["persona_slug"] in {slug for slug, _, _ in ROSTER}
    assert line["text"]


def test_pick_play_commentary_success_feast_when_not_impressive() -> None:
    line = pick_play_commentary(ok=True, impressive=False)
    assert line["kind"] == "feast"
    assert line["text"]


def test_pick_play_commentary_failure_uses_insult() -> None:
    line = pick_play_commentary(ok=False)
    assert line["kind"] == "insult"
    assert line["display_name"]
    assert line["role"]

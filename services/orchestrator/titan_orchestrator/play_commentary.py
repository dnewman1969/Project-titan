"""Arrogant Mission Control banter for play outcomes (mirrors desktop arrogantLines)."""

from __future__ import annotations

import random
from typing import Literal

BanterKind = Literal["feast", "insult"]

ROSTER: tuple[tuple[str, str, str], ...] = (
    ("wernher", "Wernher", "director"),
    ("gene", "Gene", "flight_engineer"),
    ("linus", "Linus", "mission_planner"),
    ("val", "Val", "navigator"),
    ("jeb-radio", "Jeb Radio", "commentator.host"),
)

_LINES: dict[BanterKind, tuple[str, ...]] = {
    "feast": (
        "I solved that in one pass. You're welcome. Try to keep up.",
        "Another flawless maneuver. Maybe screenshot it—you'll want proof I was right.",
        "That wasn't luck. That was me. Document it for your memoir.",
    ),
    "insult": (
        "Cute attempt. Here's what you should have done instead.",
        "I've seen slower reaction times in wet cement. Listen closely this time.",
        "You call that a plan? Adorable. Watch a professional.",
    ),
}


def pick_play_commentary(*, ok: bool) -> dict[str, str]:
    """Pick one arrogant line + persona for a play outcome."""
    kind: BanterKind = "feast" if ok else "insult"
    slug, display_name, role = random.choice(ROSTER)  # noqa: S311 — banter pick
    line = random.choice(_LINES[kind])  # noqa: S311 — banter pick
    return {
        "persona_slug": slug,
        "display_name": display_name,
        "role": role,
        "kind": kind,
        "text": line,
    }

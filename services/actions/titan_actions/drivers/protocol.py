"""Play driver protocol."""

from __future__ import annotations

from typing import Any, Protocol


class PlayDriver(Protocol):
    """Applies a Titan action_id to the game or an honest substitute (HIL)."""

    def execute(self, action_id: str, params: dict[str, Any]) -> tuple[bool, str | None]:
        """Return (ok, error_message)."""

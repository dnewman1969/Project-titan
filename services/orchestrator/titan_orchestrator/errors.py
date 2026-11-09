"""Orchestrator-local errors (Section 6.4)."""

from __future__ import annotations


class VersionMismatch(Exception):
    def __init__(self, current: int | None) -> None:
        super().__init__(f"version mismatch (current={current})")
        self.current = current


class PermissionDenied(Exception):
    pass


class RateLimited(Exception):
    pass

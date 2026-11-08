"""Error codes shared by every service and the API (Section 5.1)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

DEPENDENCIES = frozenset({"ollama", "obs", "postgres", "redis", "chroma", "game"})


class ErrorCode(StrEnum):
    VALIDATION_FAILED = "VALIDATION_FAILED"
    NOT_FOUND = "NOT_FOUND"
    UNAUTHORIZED = "UNAUTHORIZED"
    CONFLICT = "CONFLICT"
    SESSION_ALREADY_LIVE = "SESSION_ALREADY_LIVE"
    INVALID_STATE_TRANSITION = "INVALID_STATE_TRANSITION"
    VERSION_MISMATCH = "VERSION_MISMATCH"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    INTEGRATION_MISSING = "INTEGRATION_MISSING"
    INSUFFICIENT_DISK = "INSUFFICIENT_DISK"
    SAFETY_LOCKED = "SAFETY_LOCKED"
    NOT_IMPLEMENTED_IN_PHASE = "NOT_IMPLEMENTED_IN_PHASE"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL = "INTERNAL"

    @property
    def http_status(self) -> int:
        return _HTTP_STATUS[self]

    @property
    def type_uri(self) -> str:
        """RFC 7807 `type`, e.g. `https://titan.local/errors/session-already-live`."""
        return "https://titan.local/errors/" + self.value.lower().replace("_", "-")


_HTTP_STATUS: dict[ErrorCode, int] = {
    ErrorCode.VALIDATION_FAILED: 422,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.UNAUTHORIZED: 401,
    ErrorCode.CONFLICT: 409,
    ErrorCode.SESSION_ALREADY_LIVE: 409,
    ErrorCode.INVALID_STATE_TRANSITION: 409,
    ErrorCode.VERSION_MISMATCH: 412,
    ErrorCode.DEPENDENCY_UNAVAILABLE: 503,
    ErrorCode.INTEGRATION_MISSING: 424,
    ErrorCode.INSUFFICIENT_DISK: 507,
    ErrorCode.SAFETY_LOCKED: 423,
    ErrorCode.NOT_IMPLEMENTED_IN_PHASE: 501,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.INTERNAL: 500,
}


class TitanError(Exception):
    """Typed application error: `TitanError(code, detail)` (Section 9.1)."""

    def __init__(
        self,
        code: ErrorCode,
        detail: str,
        *,
        title: str | None = None,
        dependency: str | None = None,
        errors: list[dict[str, Any]] | None = None,
    ) -> None:
        if dependency is not None and dependency not in DEPENDENCIES:
            raise ValueError(f"unknown dependency {dependency!r}")
        if code is ErrorCode.DEPENDENCY_UNAVAILABLE and dependency is None:
            raise ValueError("DEPENDENCY_UNAVAILABLE requires a dependency")
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.title = title or code.value.replace("_", " ").capitalize()
        self.dependency = dependency
        self.errors = errors or []

    @property
    def http_status(self) -> int:
        return self.code.http_status

from __future__ import annotations

import pytest

from titan_core.errors import ErrorCode, TitanError

SPEC_STATUS = {
    "VALIDATION_FAILED": 422,
    "NOT_FOUND": 404,
    "UNAUTHORIZED": 401,
    "CONFLICT": 409,
    "SESSION_ALREADY_LIVE": 409,
    "INVALID_STATE_TRANSITION": 409,
    "VERSION_MISMATCH": 412,
    "DEPENDENCY_UNAVAILABLE": 503,
    "INTEGRATION_MISSING": 424,
    "INSUFFICIENT_DISK": 507,
    "SAFETY_LOCKED": 423,
    "NOT_IMPLEMENTED_IN_PHASE": 501,
    "RATE_LIMITED": 429,
    "INTERNAL": 500,
}


def test_error_codes_match_section_5_1() -> None:
    assert {code.value: code.http_status for code in ErrorCode} == SPEC_STATUS


def test_type_uri() -> None:
    assert ErrorCode.SESSION_ALREADY_LIVE.type_uri == "https://titan.local/errors/session-already-live"


def test_titan_error_fields() -> None:
    err = TitanError(ErrorCode.DEPENDENCY_UNAVAILABLE, "Ollama is not running.", dependency="ollama")
    assert err.http_status == 503
    assert err.dependency == "ollama"
    assert err.title == "Dependency unavailable"
    assert str(err) == "Ollama is not running."


def test_dependency_rules() -> None:
    with pytest.raises(ValueError, match="requires a dependency"):
        TitanError(ErrorCode.DEPENDENCY_UNAVAILABLE, "down")
    with pytest.raises(ValueError, match="unknown dependency"):
        TitanError(ErrorCode.DEPENDENCY_UNAVAILABLE, "down", dependency="mysql")

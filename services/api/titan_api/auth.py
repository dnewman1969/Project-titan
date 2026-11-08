"""Launch-token bearer authentication (Section 5.1).

Electron main generates a 32-byte random token at each launch and passes it to the
supervisor, which passes it to the API in the `TITAN_LAUNCH_TOKEN` environment variable.
"""

from __future__ import annotations

import os
import secrets
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from titan_core.errors import ErrorCode, TitanError
from titan_core.logging import get_logger

LAUNCH_TOKEN_ENV = "TITAN_LAUNCH_TOKEN"  # noqa: S105 (variable name, not a secret)
log = get_logger(__name__)

_bearer = HTTPBearer(auto_error=False)


def launch_token_from_env() -> str:
    """The launch token from the environment, or an unguessable one if it is missing.

    Without a token nobody can call authenticated routes, which is the safe failure mode.
    """
    token = os.environ.get(LAUNCH_TOKEN_ENV)
    if token:
        return token
    log.warning(
        "launch_token_missing", hint=f"set {LAUNCH_TOKEN_ENV}; authenticated routes will reject all calls"
    )
    return secrets.token_urlsafe(32)


def require_token(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> None:
    expected: str = request.app.state.launch_token
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise TitanError(ErrorCode.UNAUTHORIZED, "Missing bearer token.")
    if not secrets.compare_digest(credentials.credentials.encode(), expected.encode()):
        raise TitanError(ErrorCode.UNAUTHORIZED, "Invalid bearer token.")


Authenticated = Depends(require_token)

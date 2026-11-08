"""RFC 7807 `application/problem+json` error responses (Section 5.1)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from titan_core.errors import ErrorCode, TitanError
from titan_core.logging import get_logger

PROBLEM_JSON = "application/problem+json"
log = get_logger(__name__)

_STATUS_TO_CODE = {
    401: ErrorCode.UNAUTHORIZED,
    404: ErrorCode.NOT_FOUND,
    405: ErrorCode.NOT_FOUND,
    409: ErrorCode.CONFLICT,
    412: ErrorCode.VERSION_MISMATCH,
    422: ErrorCode.VALIDATION_FAILED,
    423: ErrorCode.SAFETY_LOCKED,
    429: ErrorCode.RATE_LIMITED,
    501: ErrorCode.NOT_IMPLEMENTED_IN_PHASE,
}


def problem(
    request: Request,
    code: ErrorCode,
    detail: str,
    *,
    status: int | None = None,
    title: str | None = None,
    errors: list[dict[str, Any]] | None = None,
    dependency: str | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": code.type_uri,
        "title": title or code.value.replace("_", " ").capitalize(),
        "status": status or code.http_status,
        "code": code.value,
        "detail": detail,
        "instance": request.url.path,
    }
    if errors:
        body["errors"] = errors
    if dependency:
        body["dependency"] = dependency
    headers = {"WWW-Authenticate": "Bearer"} if code is ErrorCode.UNAUTHORIZED else None
    return JSONResponse(body, status_code=body["status"], media_type=PROBLEM_JSON, headers=headers)


async def _titan_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, TitanError):
        raise exc
    return problem(
        request, exc.code, exc.detail, title=exc.title, errors=exc.errors, dependency=exc.dependency
    )


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    errors = [
        {"field": ".".join(str(p) for p in err["loc"] if p != "body"), "message": err["msg"]}
        for err in exc.errors()
    ]
    return problem(request, ErrorCode.VALIDATION_FAILED, "Request validation failed.", errors=errors)


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    code = _STATUS_TO_CODE.get(exc.status_code, ErrorCode.INTERNAL)
    return problem(request, code, str(exc.detail), status=exc.status_code)


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.error("unhandled_exception", path=request.url.path, exc_info=exc)
    return problem(request, ErrorCode.INTERNAL, "Internal server error.")


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(TitanError, _titan_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unhandled)

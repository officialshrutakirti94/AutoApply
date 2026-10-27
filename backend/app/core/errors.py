"""Error types and the single error envelope every endpoint returns.

Shape: ``{"error": {"code": "...", "message": "...", "details": ...}}``

The dashboard renders ``message`` verbatim, so messages are written for a person,
not for a log file. Details carry field-level information the UI can attach to
inputs, and never carry secrets.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

log = get_logger("errors")


class AppError(Exception):
    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "bad_request"
    message: str = "Something went wrong."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: Any = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.status_code = status_code or self.status_code
        self.details = details
        self.headers = headers
        super().__init__(self.message)


class AuthRequired(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "auth_required"
    message = "Sign in to continue."


class InvalidCredentials(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "invalid_credentials"
    message = "That sign-in could not be verified. Try again."


class Forbidden(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"
    message = "You do not have access to that."


class NotFound(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"
    message = "That item no longer exists."


class Conflict(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"
    message = "That conflicts with something already running."


class Unprocessable(AppError):
    status_code = 422
    code = "unprocessable"
    message = "Some fields need attention."


class PayloadTooLarge(AppError):
    status_code = 413
    code = "payload_too_large"
    message = "That file is too large."


class UnsupportedMedia(AppError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    code = "unsupported_media"
    message = "That file type is not supported."


class RateLimited(AppError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"
    message = "Too many attempts. Wait a minute and try again."


class UpstreamUnavailable(AppError):
    status_code = status.HTTP_502_BAD_GATEWAY
    code = "upstream_unavailable"
    message = "A service we depend on is unavailable. Try again shortly."


class PolicyBlocked(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "policy_blocked"
    message = "Safety rules do not allow this right now."


def _envelope(code: str, message: str, details: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        payload["details"] = details
    return {"error": payload}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.details),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {
                "field": ".".join(str(part) for part in error.get("loc", ())[1:]) or "body",
                "message": error.get("msg", "Invalid value"),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_envelope("validation_error", "Some fields need attention.", fields),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception(
            "unhandled_error",
            path=request.url.path,
            method=request.method,
            error_type=type(exc).__name__,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope("internal_error", "Something went wrong on our side. Try again."),
        )

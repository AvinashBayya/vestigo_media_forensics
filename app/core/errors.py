"""Application errors and the single JSON error envelope used by every endpoint."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import exception_location, get_logger, log_event
from app.schemas.common import ErrorBody, ErrorCode, ErrorResponse

logger = get_logger("errors")

_HTTP_STATUS_CODES = {
    404: (ErrorCode.NOT_FOUND, "Resource not found."),
    405: (ErrorCode.METHOD_NOT_ALLOWED, "Method not allowed."),
    413: (ErrorCode.FILE_TOO_LARGE, "Request body is too large."),
}


class AppError(Exception):
    def __init__(
        self, status_code: int, code: ErrorCode, message: str, details: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def error_response(
    status_code: int,
    code: ErrorCode,
    message: str,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details or {}))
    return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"), headers=headers)


async def _app_error(_: Request, exc: AppError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message, exc.details)


async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Only location, message, and type are returned; submitted values are not echoed back.
    errors = [
        {
            "loc": [str(part) for part in err.get("loc", ())],
            "message": err.get("msg", ""),
            "type": err.get("type", ""),
        }
        for err in exc.errors()
    ]
    return error_response(422, ErrorCode.VALIDATION_ERROR, "Request validation failed.", {"errors": errors})


async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code, message = _HTTP_STATUS_CODES.get(exc.status_code, (ErrorCode.HTTP_ERROR, str(exc.detail)))
    return error_response(exc.status_code, code, message, headers=getattr(exc, "headers", None))


async def _unhandled_error(_: Request, exc: Exception) -> JSONResponse:
    log_event(
        logger,
        logging.ERROR,
        "request.unhandled_error",
        error_type=type(exc).__name__,
        location=exception_location(exc),
    )
    return error_response(500, ErrorCode.INTERNAL_ERROR, "An internal error occurred.")


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unhandled_error)

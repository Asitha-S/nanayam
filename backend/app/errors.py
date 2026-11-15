"""Error shape from contract section 0: {"error": {"code", "message", "details"}}."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("naanayam")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}


def bad_request(message: str, **details) -> ApiError:
    return ApiError(400, "BAD_REQUEST", message, details)


def not_found(message: str, **details) -> ApiError:
    return ApiError(404, "NOT_FOUND", message, details)


def duplicate_conflict(message: str, **details) -> ApiError:
    return ApiError(409, "DUPLICATE_CONFLICT", message, details)


def invalid_state(message: str, **details) -> ApiError:
    return ApiError(409, "INVALID_STATE", message, details)


def validation_error(message: str, **details) -> ApiError:
    return ApiError(422, "VALIDATION_ERROR", message, details)


def sarvam_unavailable(message: str, **details) -> ApiError:
    return ApiError(503, "SARVAM_UNAVAILABLE", message, details)


def cache_miss(message: str, **details) -> ApiError:
    return ApiError(503, "CACHE_MISS", message, details)


def rate_limited(message: str, **details) -> ApiError:
    return ApiError(429, "RATE_LIMITED", message, details)


def error_body(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def _json(status: int, code: str, message: str, details: dict | None = None) -> JSONResponse:
    return JSONResponse(status_code=status, content=error_body(code, message, details))


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return _json(exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        errors = exc.errors()
        if any(e.get("type") == "json_invalid" for e in errors):
            return _json(400, "BAD_REQUEST", "Malformed JSON body")
        problems = [
            {
                "field": ".".join(str(p) for p in e.get("loc", ())[1:]) or None,
                "message": e.get("msg", ""),
                "type": e.get("type", ""),
            }
            for e in errors
        ]
        first = problems[0] if problems else {"field": None, "message": "invalid request"}
        message = f"{first['field']}: {first['message']}" if first["field"] else first["message"]
        return _json(422, "VALIDATION_ERROR", message, {"field": first["field"], "errors": problems})

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return _json(404, "NOT_FOUND", "Not found")
        if exc.status_code in (400, 405, 415):
            return _json(400, "BAD_REQUEST", str(exc.detail))
        return _json(500, "INTERNAL_ERROR", str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("Unhandled error")
        return _json(500, "INTERNAL_ERROR", "Internal error")

"""Consistent error bodies (`{"detail": ...}`) and database-error mapping.

Postgres error messages can contain row values ("Failing row contains ..."), and some
rows hold personal data. Database errors are therefore never echoed or logged
verbatim: only the SQLSTATE and the constraint name are used.
"""

import logging
from typing import Any, cast

import psycopg
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from psycopg import errors as pg_errors
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ErrorOut(BaseModel):
    detail: str


class UnprocessableOut(BaseModel):
    """422: a rule message (string) from the API, or FastAPI's list of field errors."""

    detail: str | list[dict[str, Any]]


def error_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI `responses=` entry for the listed error status codes."""
    return {code: {"model": UnprocessableOut if code == 422 else ErrorOut} for code in codes}


def not_found(what: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{what} not found")


def conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def unprocessable(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=detail)


def _json(code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=code, content={"detail": detail})


# Starlette's handler signature takes a plain Exception; the registration below
# guarantees the concrete psycopg class.
def _integrity_error(_: Request, exc: Exception) -> JSONResponse:
    constraint = cast(psycopg.Error, exc).diag.constraint_name or "unknown"
    if isinstance(exc, pg_errors.UniqueViolation):
        return _json(status.HTTP_409_CONFLICT, f"conflicts with an existing row ({constraint})")
    if isinstance(exc, pg_errors.ForeignKeyViolation):
        return _json(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"referenced row does not exist ({constraint})"
        )
    return _json(
        status.HTTP_422_UNPROCESSABLE_CONTENT, f"violates database constraint ({constraint})"
    )


def _operational_error(_: Request, exc: Exception) -> JSONResponse:
    # Also covers psycopg_pool.PoolTimeout (a subclass of OperationalError).
    sqlstate = cast(psycopg.Error, exc).sqlstate
    logger.warning("database unavailable: %s (sqlstate=%s)", type(exc).__name__, sqlstate)
    return _json(status.HTTP_503_SERVICE_UNAVAILABLE, "database unavailable")


def _database_error(request: Request, exc: Exception) -> JSONResponse:
    sqlstate = cast(psycopg.Error, exc).sqlstate
    logger.error(
        "database error on %s %s: %s (sqlstate=%s)",
        request.method,
        request.url.path,
        type(exc).__name__,
        sqlstate,
    )
    return _json(status.HTTP_500_INTERNAL_SERVER_ERROR, "database error")


def install_error_handlers(app: FastAPI) -> None:
    # Starlette picks the handler registered for the nearest class in the exception's MRO.
    app.add_exception_handler(psycopg.IntegrityError, _integrity_error)
    app.add_exception_handler(psycopg.OperationalError, _operational_error)
    app.add_exception_handler(psycopg.Error, _database_error)

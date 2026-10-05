"""Connection checks for the admin Settings page."""

import time

from fastapi import APIRouter
from pydantic import BaseModel

from fhc_api.common.errors import error_responses
from fhc_api.db import DbConn

router = APIRouter(prefix="/system", tags=["system"])


class DbCheckOut(BaseModel):
    ok: bool
    latency_ms: float
    role: str
    server_version: str


@router.get(
    "/db",
    operation_id="check_database",
    response_model=DbCheckOut,
    responses=error_responses(503),
)
def check_database(conn: DbConn) -> DbCheckOut:
    """200 when a query round-trip succeeds; 503 `database unavailable` otherwise."""
    started = time.perf_counter()
    row = conn.execute(
        "select current_user as role, current_setting('server_version') as server_version"
    ).fetchone()
    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    return DbCheckOut(
        ok=row is not None,
        latency_ms=latency_ms,
        role=row["role"] if row else "",
        server_version=row["server_version"] if row else "",
    )

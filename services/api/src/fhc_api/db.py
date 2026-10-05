"""Postgres connection pool and the per-request connection dependency.

Connections run in autocommit mode: a single read is its own statement, and every
write path opens an explicit `with conn.transaction():` block in the service layer.
The write has therefore committed before a router triggers side effects such as web
revalidation. Tests replace `get_conn` with a connection inside a rolled-back
transaction, which turns those blocks into savepoints.
"""

from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import Depends, Request
from psycopg import Connection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool

Conn = Connection[DictRow]


def create_pool(database_url: str) -> ConnectionPool[Conn]:
    kwargs: dict[str, Any] = {"autocommit": True, "row_factory": dict_row}
    return ConnectionPool(
        database_url,
        connection_class=Connection[DictRow],
        kwargs=kwargs,
        min_size=1,
        max_size=5,
        timeout=10.0,
        open=False,
        name="fhc_api",
    )


def get_conn(request: Request) -> Iterator[Conn]:
    pool: ConnectionPool[Conn] = request.app.state.pool
    with pool.connection() as conn:
        yield conn


DbConn = Annotated[Conn, Depends(get_conn)]

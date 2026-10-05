"""Postgres connection pool and the per-request connection dependency.

Connections run in autocommit mode: a single read is its own statement, and every
write path opens an explicit `with conn.transaction():` block in the service layer.
The write has therefore committed before a router triggers side effects such as web
revalidation. Tests replace `get_conn` and `get_conn_factory` with a connection inside a
rolled-back transaction, which turns those blocks into savepoints.
"""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
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


type ConnFactory = Callable[[], AbstractContextManager[Conn]]


def get_conn_factory(request: Request) -> ConnFactory:
    """For handlers that must release the connection before slow work (a network fetch):
    `with open_conn() as conn: ...` returns it to the pool at the end of the block."""
    pool: ConnectionPool[Conn] = request.app.state.pool
    return pool.connection


ConnFactoryDep = Annotated[ConnFactory, Depends(get_conn_factory)]

"""Dynamic INSERT/UPDATE for `app.*` tables. Column names come from Pydantic model
fields (never from request keys) and are quoted with `sql.Identifier`; values are
always bound parameters."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from psycopg import sql
from psycopg.rows import DictRow

from fhc_api.db import Conn


def insert_row(conn: Conn, table: str, values: Mapping[str, Any]) -> DictRow:
    query = sql.SQL("insert into {table} ({columns}) values ({values}) returning *").format(
        table=sql.Identifier("app", table),
        columns=sql.SQL(", ").join(map(sql.Identifier, values)),
        values=sql.SQL(", ").join(map(sql.Placeholder, values)),
    )
    row = conn.execute(query, values).fetchone()
    if row is None:  # pragma: no cover - INSERT ... RETURNING always returns the row
        raise RuntimeError(f"insert into {table} returned no row")
    return row


def select_page(
    conn: Conn,
    table: str,
    *,
    where: str,
    order_by: str,
    params: Mapping[str, Any],
    limit: int,
    offset: int,
) -> tuple[list[DictRow], int]:
    """One page of rows plus the total match count. `where` and `order_by` must be
    constant SQL fragments (values go through `params`)."""
    fragments = {"table": sql.Identifier("app", table), "where": sql.SQL(where)}
    page_params = {**params, "_limit": limit, "_offset": offset}
    rows = conn.execute(
        sql.SQL(
            "select *, count(*) over () as _total from {table} where {where}"
            " order by {order_by} limit %(_limit)s offset %(_offset)s"
        ).format(**fragments, order_by=sql.SQL(order_by)),
        page_params,
    ).fetchall()
    if rows:
        return rows, int(rows[0]["_total"])
    # Past the last page the window count is unavailable; count separately.
    total = conn.execute(
        sql.SQL("select count(*) as n from {table} where {where}").format(**fragments), params
    ).fetchone()
    return rows, int(total["n"]) if total else 0


def update_row(conn: Conn, table: str, row_id: UUID, values: Mapping[str, Any]) -> DictRow | None:
    """Update by primary key `id`; None when no such row exists."""
    query = sql.SQL("update {table} set {assignments} where id = {id} returning *").format(
        table=sql.Identifier("app", table),
        assignments=sql.SQL(", ").join(
            sql.SQL("{} = {}").format(sql.Identifier(column), sql.Placeholder(column))
            for column in values
        ),
        id=sql.Placeholder("_id"),
    )
    return conn.execute(query, {**values, "_id": row_id}).fetchone()

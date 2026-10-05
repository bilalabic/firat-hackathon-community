from collections.abc import Sequence
from typing import Literal
from uuid import UUID

from psycopg.rows import DictRow

from fhc_api.common.sql import select_page, update_row
from fhc_api.db import Conn

ApplicationTable = Literal["community_applications", "team_applications"]


def list_page(
    conn: Conn, table: ApplicationTable, *, statuses: Sequence[str], limit: int, offset: int
) -> tuple[list[DictRow], int]:
    return select_page(
        conn,
        table,
        where="status = any(%(statuses)s::app.application_status[])" if statuses else "true",
        order_by="created_at desc, id",
        params={"statuses": list(statuses)},
        limit=limit,
        offset=offset,
    )


def set_status(conn: Conn, table: ApplicationTable, row_id: UUID, status: str) -> DictRow | None:
    return update_row(conn, table, row_id, {"status": status})

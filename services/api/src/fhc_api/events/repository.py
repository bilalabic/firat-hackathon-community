"""Plain parameterized SQL for `app.events`."""

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any
from uuid import UUID

from psycopg.rows import DictRow

from fhc_api.common.sql import insert_row, select_page, update_row
from fhc_api.db import Conn

# Published events that have not ended yet, in each event's own timezone.
UPCOMING_SQL = (
    "status = 'published' and coalesce(end_date, start_date) >= (now() at time zone timezone)::date"
)
# Published events whose (inclusive) deadline is within the next N days, N = %(days)s.
CLOSING_SQL = (
    "status = 'published'"
    " and application_deadline between (now() at time zone timezone)::date"
    " and (now() at time zone timezone)::date + %(days)s::int"
)


def get(conn: Conn, event_id: UUID, *, for_update: bool = False) -> DictRow | None:
    query = (
        "select * from app.events where id = %s for update"
        if for_update
        else "select * from app.events where id = %s"
    )
    return conn.execute(query, (event_id,)).fetchone()


def list_page(
    conn: Conn,
    *,
    statuses: Sequence[str],
    upcoming: bool,
    closing_within_days: int | None,
    limit: int,
    offset: int,
) -> tuple[list[DictRow], int]:
    conditions = ["true"]
    params: dict[str, Any] = {}
    if statuses:
        conditions.append("status = any(%(statuses)s::app.event_status[])")
        params["statuses"] = list(statuses)
    if upcoming:
        conditions.append(UPCOMING_SQL)
    if closing_within_days is not None:
        conditions.append(CLOSING_SQL)
        params["days"] = closing_within_days
    return select_page(
        conn,
        "events",
        where=" and ".join(f"({condition})" for condition in conditions),
        order_by="updated_at desc, id",
        params=params,
        limit=limit,
        offset=offset,
    )


def slug_exists(conn: Conn, slug: str) -> bool:
    return conn.execute("select 1 from app.events where slug = %s", (slug,)).fetchone() is not None


def insert(conn: Conn, values: Mapping[str, Any]) -> DictRow:
    return insert_row(conn, "events", values)


def update(conn: Conn, event_id: UUID, values: Mapping[str, Any]) -> DictRow:
    row = update_row(conn, "events", event_id, values)
    if row is None:  # pragma: no cover - the caller holds a row lock
        raise RuntimeError("event disappeared during update")
    return row


def find_duplicate_candidates(
    conn: Conn, event_id: UUID, official_url_normalized: str, start_date: date | None
) -> list[DictRow]:
    """Other events sharing the normalized official URL or the start date. Title
    matching happens in Python (Turkish folding)."""
    return conn.execute(
        "select id, slug, title, status, start_date, official_url_normalized"
        " from app.events"
        " where id <> %(id)s"
        " and (official_url_normalized = %(url)s"
        "      or (%(start)s::date is not null and start_date = %(start)s::date))"
        " order by created_at",
        {"id": event_id, "url": official_url_normalized, "start": start_date},
    ).fetchall()

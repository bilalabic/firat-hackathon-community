from collections.abc import Mapping
from typing import Any
from uuid import UUID

from psycopg.rows import DictRow

from fhc_api.common.sql import insert_row, update_row
from fhc_api.db import Conn

_EVENT_SOURCE_SELECT = (
    "select es.*, s.name as source_name, s.tier as source_tier"
    " from app.event_sources es left join app.sources s on s.id = es.source_id"
)


def list_sources(conn: Conn) -> list[DictRow]:
    return conn.execute("select * from app.sources order by tier, name").fetchall()


def insert_source(conn: Conn, values: Mapping[str, Any]) -> DictRow:
    return insert_row(conn, "sources", values)


def update_source(conn: Conn, source_id: UUID, values: Mapping[str, Any]) -> DictRow | None:
    return update_row(conn, "sources", source_id, values)


def get_source(conn: Conn, source_id: UUID) -> DictRow | None:
    return conn.execute("select * from app.sources where id = %s", (source_id,)).fetchone()


def list_event_sources(conn: Conn, event_id: UUID) -> list[DictRow]:
    return conn.execute(
        _EVENT_SOURCE_SELECT + " where es.event_id = %s order by es.first_seen_at, es.id",
        (event_id,),
    ).fetchall()


def get_event_source(conn: Conn, event_source_id: UUID) -> DictRow | None:
    return conn.execute(
        _EVENT_SOURCE_SELECT + " where es.id = %s",
        (event_source_id,),
    ).fetchone()


def insert_event_source(conn: Conn, values: Mapping[str, Any]) -> UUID:
    event_source_id: UUID = insert_row(conn, "event_sources", values)["id"]
    return event_source_id


def delete_event_source(conn: Conn, event_id: UUID, event_source_id: UUID) -> bool:
    cursor = conn.execute(
        "delete from app.event_sources where event_id = %s and id = %s",
        (event_id, event_source_id),
    )
    return cursor.rowcount == 1

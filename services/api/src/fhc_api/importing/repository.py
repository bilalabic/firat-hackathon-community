"""Plain parameterized SQL for `app.runs` and `app.event_field_evidence` (V1.2)."""

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from psycopg.rows import DictRow
from psycopg.types.json import Jsonb

from fhc_api.common.sql import insert_row, select_page
from fhc_api.db import Conn

MANUAL_SOURCE = "Manual entry"


def find_event_by_url(conn: Conn, urls_normalized: Sequence[str]) -> DictRow | None:
    """The oldest event whose normalized official URL, or one of whose event source URLs
    (an import stores the page it read there, e.g. a redirect target), is one of
    `urls_normalized`."""
    return conn.execute(
        "select id, slug, title, status from app.events e"
        " where e.official_url_normalized = any(%(urls)s)"
        "    or exists (select 1 from app.event_sources es"
        "               where es.event_id = e.id and es.url_normalized = any(%(urls)s))"
        " order by e.created_at, e.id limit 1",
        {"urls": list(urls_normalized)},
    ).fetchone()


def lock_key(url_normalized: str) -> str:
    return f"url_import:{url_normalized}"


def lock_urls(conn: Conn, urls_normalized: Sequence[str]) -> None:
    """Transaction-scoped advisory locks, one per URL, taken in sorted order (no deadlock):
    concurrent imports that share any URL (requested or redirect target) run one after
    the other. Released at commit or rollback."""
    for url in sorted(set(urls_normalized)):
        conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (lock_key(url),))


def manual_source_id(conn: Conn) -> UUID | None:
    row = conn.execute("select id from app.sources where name = %s", (MANUAL_SOURCE,)).fetchone()
    return row["id"] if row else None


def insert_run(conn: Conn, *, kind: str, input_: Mapping[str, Any]) -> DictRow:
    return insert_row(conn, "runs", {"kind": kind, "input": Jsonb(dict(input_))})


def finish_run(
    conn: Conn,
    run_id: UUID,
    *,
    status: str,
    stats: Mapping[str, Any],
    error: str | None = None,
    event_id: UUID | None = None,
) -> DictRow:
    # The database clock, like `started_at` (the API and the database may run on
    # different machines).
    row = conn.execute(
        "update app.runs set status = %(status)s, stats = %(stats)s, error = %(error)s,"
        " event_id = %(event_id)s, finished_at = greatest(now(), started_at)"
        " where id = %(id)s returning *",
        {
            "status": status,
            "stats": Jsonb(dict(stats)),
            "error": error,
            "event_id": event_id,
            "id": run_id,
        },
    ).fetchone()
    if row is None:  # pragma: no cover - the run was inserted by the same request
        raise RuntimeError("run disappeared")
    return row


def list_runs(conn: Conn, *, limit: int, offset: int) -> tuple[list[DictRow], int]:
    return select_page(
        conn,
        "runs",
        where="true",
        order_by="started_at desc, id",
        params={},
        limit=limit,
        offset=offset,
    )


def insert_evidence(conn: Conn, rows: Sequence[Mapping[str, Any]]) -> None:
    for values in rows:
        insert_row(conn, "event_field_evidence", values)


def latest_evidence(conn: Conn, event_id: UUID) -> list[DictRow]:
    """The rows of the event's most recent extraction (one run)."""
    return conn.execute(
        "with latest as ("
        "  select run_id, extracted_at from app.event_field_evidence"
        "  where event_id = %(id)s order by extracted_at desc, id limit 1"
        ")"
        " select e.* from app.event_field_evidence e, latest"
        " where e.event_id = %(id)s"
        "   and e.run_id is not distinct from latest.run_id"
        "   and (latest.run_id is not null or e.extracted_at = latest.extracted_at)"
        " order by e.field, e.value_text is null, e.id",
        {"id": event_id},
    ).fetchall()


def get_run(conn: Conn, run_id: UUID) -> DictRow | None:
    return conn.execute("select * from app.runs where id = %s", (run_id,)).fetchone()

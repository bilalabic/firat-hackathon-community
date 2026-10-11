"""Plain SQL for `app.publications` (Telegram channel posts). Functions run on the caller's
connection; the service decides the transactions and never holds one during a Bot API
call."""

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from psycopg import sql
from psycopg.rows import DictRow

from fhc_api.common.sql import insert_row, select_page, update_row
from fhc_api.db import Conn

PLATFORM = "telegram"
# A draft (claimed before the Bot API call) older than this was left by a crash, or by a
# database write that failed after the call: its outcome is unknown.
STALE_DRAFT_MINUTES = 10
# An update claim (`updating_since`) older than this was left the same way; it no longer
# blocks a new update (editing again is harmless).
STALE_UPDATE_MINUTES = 10
# Computed by the database clock: `stale` (a draft older than STALE_DRAFT_MINUTES) and
# `updating` (an update claimed less than STALE_UPDATE_MINUTES ago).
_FLAGS = sql.SQL(
    "status = 'draft' and created_at < now() - make_interval(mins => %s) as stale,"
    " coalesce(updating_since >= now() - make_interval(mins => %s), false) as updating"
)
_FLAG_PARAMS = (STALE_DRAFT_MINUTES, STALE_UPDATE_MINUTES)
# The draft, uncertain or live post: at most one per event (unique index
# publications_one_live_per_event). Same rule as `admin_bot.store._MARKER_SQL`.
_LIVE_SELECT = sql.SQL(
    "select *, {flags} from app.publications where platform = 'telegram'"
    " and (status in ('draft', 'sent', 'edited') or uncertain)"
).format(flags=_FLAGS)


def _lock(for_update: bool) -> sql.SQL:
    return sql.SQL(" for update" if for_update else "")


def live_post(conn: Conn, event_id: UUID, *, for_update: bool = False) -> DictRow | None:
    """The draft, uncertain or live post of the event, with `stale` and `updating`."""
    query = _LIVE_SELECT + sql.SQL(" and event_id = %s") + _lock(for_update)
    return conn.execute(query, (*_FLAG_PARAMS, event_id)).fetchone()


def live_posts(conn: Conn, event_ids: Sequence[UUID]) -> dict[UUID, DictRow]:
    rows = conn.execute(
        _LIVE_SELECT + sql.SQL(" and event_id = any(%s)"), (*_FLAG_PARAMS, list(event_ids))
    ).fetchall()
    return {row["event_id"]: row for row in rows}


def get(conn: Conn, publication_id: UUID, *, for_update: bool = False) -> DictRow | None:
    """One post, with `stale` and `updating`."""
    query = sql.SQL("select *, {flags} from app.publications where id = %s{lock}").format(
        flags=_FLAGS, lock=_lock(for_update)
    )
    return conn.execute(query, (*_FLAG_PARAMS, publication_id)).fetchone()


def insert(conn: Conn, values: Mapping[str, Any]) -> DictRow:
    return insert_row(conn, "publications", {"platform": PLATFORM, **values})


def update(conn: Conn, publication_id: UUID, values: Mapping[str, Any]) -> DictRow:
    row = update_row(conn, "publications", publication_id, values)
    if row is None:  # pragma: no cover - publications are never deleted
        raise RuntimeError("publication disappeared during update")
    return row


def claim_update(conn: Conn, publication_id: UUID) -> DictRow:
    """Mark an edit as in progress (database clock) before the Bot API call."""
    row = conn.execute(
        "update app.publications set updating_since = now() where id = %s returning *",
        (publication_id,),
    ).fetchone()
    if row is None:  # pragma: no cover - publications are never deleted
        raise RuntimeError("publication disappeared during update")
    return row


def history(conn: Conn, event_id: UUID) -> list[DictRow]:
    return conn.execute(
        "select * from app.publications where event_id = %s and platform = %s"
        " order by created_at desc, id",
        (event_id, PLATFORM),
    ).fetchall()


def audit_entries(conn: Conn, event_id: UUID) -> list[DictRow]:
    return conn.execute(
        "select actor, action, detail, at from app.admin_actions"
        " where entity_type = 'event' and entity_id = %s and action like 'telegram\\_%%'"
        " order by at desc, id",
        (event_id,),
    ).fetchall()


def page_of_events(conn: Conn, *, limit: int, offset: int) -> tuple[list[DictRow], int]:
    """Published events plus events that are no longer public but still have a post
    (those first, since they may need a decision)."""
    return select_page(
        conn,
        "events",
        where=(
            "status = 'published' or exists (select 1 from app.publications p"
            " where p.event_id = events.id and p.platform = 'telegram'"
            " and (p.status in ('draft', 'sent', 'edited') or p.uncertain))"
        ),
        order_by="(status = 'published'), start_date desc nulls last, id",
        params={},
        limit=limit,
        offset=offset,
    )


def channel_marker(post: Mapping[str, Any] | None) -> str:
    """Identifies the draft/uncertain/live post for the admin bot's state tokens: changes
    when a post is created, edited or removed. Same as `admin_bot.store._MARKER_SQL`."""
    return "" if post is None else f"{post['id']}:{post['content_version']}"

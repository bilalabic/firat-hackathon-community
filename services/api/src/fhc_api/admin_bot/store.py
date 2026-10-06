"""Plain SQL for the admin bot tables (`app.bot_state`, `app.bot_notifications`,
`app.bot_pending_replies`). Functions run on the caller's connection; the caller decides
the transaction boundaries and never holds a connection during a Telegram call."""

from collections.abc import Sequence
from uuid import UUID

from psycopg import sql
from psycopg.rows import DictRow

from fhc_api.admin_bot.codec import Kind
from fhc_api.common.audit import EntityType
from fhc_api.db import Conn

APPLICATION_TABLES: dict[EntityType, str] = {
    "community_application": "community_applications",
    "team_application": "team_applications",
}
# A claimed slot whose send never completed (crash between claim and update) is freed
# after this long, so the notification is retried.
STALE_CLAIM_MINUTES = 10


# --- state ---------------------------------------------------------------------------


def _offset_key(bot_id: int) -> str:
    return f"admin_bot.{bot_id}.update_offset"


def load_offset(conn: Conn, bot_id: int) -> int | None:
    row = conn.execute(
        "select value from app.bot_state where key = %s", (_offset_key(bot_id),)
    ).fetchone()
    return int(row["value"]) if row else None


def save_offset(conn: Conn, bot_id: int, offset: int) -> None:
    conn.execute(
        "insert into app.bot_state (key, value) values (%s, %s)"
        " on conflict (key) do update set value = excluded.value",
        (_offset_key(bot_id), str(offset)),
    )


# --- entities ------------------------------------------------------------------------


def load_entity(
    conn: Conn, entity_type: EntityType, entity_id: UUID, *, for_update: bool = False
) -> DictRow | None:
    table = "events" if entity_type == "event" else APPLICATION_TABLES[entity_type]
    query = sql.SQL("select * from {table} where id = %s{lock}").format(
        table=sql.Identifier("app", table), lock=sql.SQL(" for update" if for_update else "")
    )
    return conn.execute(query, (entity_id,)).fetchone()


def events_in_status(conn: Conn, status: str, limit: int) -> list[DictRow]:
    return conn.execute(
        "select * from app.events where status = %s::app.event_status"
        " order by updated_at, id limit %s",
        (status, limit),
    ).fetchall()


def new_applications(conn: Conn, entity_type: EntityType, limit: int) -> list[DictRow]:
    query = sql.SQL(
        "select * from {table} where status = 'new' order by created_at, id limit %s"
    ).format(table=sql.Identifier("app", APPLICATION_TABLES[entity_type]))
    return conn.execute(query, (limit,)).fetchall()


# --- notifications -------------------------------------------------------------------


def live_slots(conn: Conn, kind: Kind, entity_ids: Sequence[UUID]) -> set[tuple[UUID, str, int]]:
    """(entity id, state token, chat id) of notifications that block a new send: every row
    except the expired ones (the partial unique index uses the same rule)."""
    rows = conn.execute(
        "select entity_id, state_token, chat_id from app.bot_notifications"
        " where kind = %s and entity_id = any(%s)"
        " and (resolution is null or resolution <> 'expired')",
        (kind, list(entity_ids)),
    ).fetchall()
    return {(row["entity_id"], row["state_token"], row["chat_id"]) for row in rows}


def claim(
    conn: Conn, entity_type: EntityType, entity_id: UUID, kind: Kind, token: str, chat_id: int
) -> UUID | None:
    """Reserve the slot before sending. None when another scan (or an earlier run) has it."""
    row = conn.execute(
        "insert into app.bot_notifications (entity_type, entity_id, kind, state_token, chat_id)"
        " values (%s, %s, %s, %s, %s) on conflict do nothing returning id",
        (entity_type, entity_id, kind, token, chat_id),
    ).fetchone()
    return row["id"] if row else None


def mark_sent(conn: Conn, notification_id: UUID, message_id: int) -> None:
    conn.execute(
        "update app.bot_notifications set message_id = %s, sent_at = now() where id = %s",
        (message_id, notification_id),
    )


def release_claim(conn: Conn, notification_id: UUID) -> None:
    conn.execute(
        "delete from app.bot_notifications where id = %s and message_id is null",
        (notification_id,),
    )


def delete_stale_claims(conn: Conn) -> int:
    return conn.execute(
        "delete from app.bot_notifications where message_id is null"
        " and created_at < now() - make_interval(mins => %s)",
        (STALE_CLAIM_MINUTES,),
    ).rowcount


def unresolved_with_state(conn: Conn, max_age_h: float) -> list[DictRow]:
    """Sent, unresolved notifications with the current state of their entity (null
    columns when the entity no longer exists) and whether their buttons are too old."""
    return conn.execute(
        "select n.id, n.entity_type, n.entity_id, n.kind, n.state_token, n.chat_id,"
        " n.message_id, n.sent_at < now() - make_interval(secs => %s) as expired,"
        " e.title, e.status::text as event_status,"
        " coalesce(e.updated_at, c.updated_at, t.updated_at) as updated_at,"
        " coalesce(c.status, t.status)::text as application_status,"
        " coalesce(c.full_name, t.full_name) as full_name"
        " from app.bot_notifications n"
        " left join app.events e on n.entity_type = 'event' and e.id = n.entity_id"
        " left join app.community_applications c"
        "   on n.entity_type = 'community_application' and c.id = n.entity_id"
        " left join app.team_applications t"
        "   on n.entity_type = 'team_application' and t.id = n.entity_id"
        " where n.resolved_at is null and n.message_id is not null"
        " order by n.sent_at",
        (max_age_h * 3600,),
    ).fetchall()


def find_by_message(
    conn: Conn, chat_id: int, message_id: int, max_age_h: float, confirm_ttl_s: float
) -> DictRow | None:
    """The notification shown in this message, locked, with `expired` (button age) and
    `confirm_fresh` (a recent first Publish/Reject press) computed by the database clock."""
    return conn.execute(
        "select *, sent_at < now() - make_interval(secs => %s) as expired,"
        " coalesce(confirm_at >= now() - make_interval(secs => %s), false) as confirm_fresh"
        " from app.bot_notifications where chat_id = %s and message_id = %s for update",
        (max_age_h * 3600, confirm_ttl_s, chat_id, message_id),
    ).fetchone()


def set_confirm(conn: Conn, notification_id: UUID, action: str | None) -> None:
    """Record (or clear, with None) the first step of a two-step confirmation."""
    conn.execute(
        "update app.bot_notifications set confirm_action = %s,"
        " confirm_at = case when %s::text is null then null else now() end where id = %s",
        (action, action, notification_id),
    )


def get_notification(conn: Conn, notification_id: UUID) -> DictRow | None:
    return conn.execute(
        "select * from app.bot_notifications where id = %s for update", (notification_id,)
    ).fetchone()


def resolve_ids(conn: Conn, ids: Sequence[UUID], resolution: str) -> list[DictRow]:
    return conn.execute(
        "update app.bot_notifications set resolved_at = now(), resolution = %s"
        " where id = any(%s) and resolved_at is null returning chat_id, message_id",
        (resolution, list(ids)),
    ).fetchall()


def resolve_entity(
    conn: Conn, entity_type: EntityType, entity_id: UUID, kind: Kind, resolution: str
) -> list[DictRow]:
    """Resolve every admin's open message about this entity (one decision covers all)."""
    return conn.execute(
        "update app.bot_notifications set resolved_at = now(), resolution = %s"
        " where entity_type = %s and entity_id = %s and kind = %s"
        " and resolved_at is null and message_id is not null"
        " returning chat_id, message_id",
        (resolution, entity_type, entity_id, kind),
    ).fetchall()


# --- pending replies -----------------------------------------------------------------


def add_pending_reply(
    conn: Conn,
    *,
    chat_id: int,
    prompt_message_id: int,
    notification_id: UUID,
    entity_id: UUID,
    action: str,
    token: str,
    ttl_minutes: int,
) -> None:
    conn.execute(
        "insert into app.bot_pending_replies"
        " (chat_id, prompt_message_id, notification_id, entity_id, action, state_token,"
        "  expires_at)"
        " values (%s, %s, %s, %s, %s, %s, now() + make_interval(mins => %s))",
        (chat_id, prompt_message_id, notification_id, entity_id, action, token, ttl_minutes),
    )


def get_pending_reply(conn: Conn, chat_id: int, prompt_message_id: int) -> DictRow | None:
    """The open prompt, locked; `expired` is computed by the database clock."""
    return conn.execute(
        "select *, expires_at < now() as expired from app.bot_pending_replies"
        " where chat_id = %s and prompt_message_id = %s for update",
        (chat_id, prompt_message_id),
    ).fetchone()


def delete_pending_reply(conn: Conn, pending_id: UUID) -> None:
    conn.execute("delete from app.bot_pending_replies where id = %s", (pending_id,))


def delete_expired_replies(conn: Conn) -> int:
    return conn.execute("delete from app.bot_pending_replies where expires_at < now()").rowcount


def counts(conn: Conn) -> tuple[int, int]:
    """(unresolved sent notifications, open reason prompts)."""
    row = conn.execute(
        "select"
        " (select count(*) from app.bot_notifications"
        "   where resolved_at is null and message_id is not null) as notifications,"
        " (select count(*) from app.bot_pending_replies where expires_at >= now()) as replies"
    ).fetchone()
    return (int(row["notifications"]), int(row["replies"])) if row else (0, 0)

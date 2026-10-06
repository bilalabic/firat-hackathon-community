"""Outbox scan: send one message per entity state and admin chat, and retire messages
whose entity changed elsewhere.

Idempotency: a slot `(entity, kind, state token, chat)` is claimed in
`app.bot_notifications` (unique partial index) *before* sendMessage, so neither a restart
nor a concurrent scan sends the same notification twice. A failed send releases the
claim so the next scan retries it. Known edge: when the request reached Telegram but the
response was lost (timeout), the retry can send one duplicate; that is preferred over
losing a review notification. A claim left behind by a crash is freed after
`STALE_CLAIM_MINUTES`.
"""

import time
from collections.abc import Mapping
from dataclasses import dataclass
from functools import partial
from typing import Any
from uuid import UUID

from fhc_api.admin_bot import messages, store
from fhc_api.admin_bot.codec import Kind
from fhc_api.admin_bot.context import KIND_STATUS, BotContext, best_effort, current_token, logger
from fhc_api.common.audit import EntityType
from fhc_api.db import Conn
from fhc_api.events import repository as events_repository
from fhc_api.review.signals import compute_signals, count_by_tier, find_duplicates
from fhc_api.sources import repository as sources_repository
from fhc_api.telegram.client import TelegramAPIError, TelegramError
from fhc_api.telegram.formatting import escape_html

# Entities per kind and scan; the rest follow in later scans.
MAX_ENTITIES_PER_KIND = 10
# Telegram asks bots not to send more than about one message per second to one chat.
SEND_PACING_S = 1.0
# After "bot was blocked" / "can't initiate conversation" (403), stop trying that chat
# for a while instead of failing every scan.
BLOCKED_CHAT_PAUSE_S = 15 * 60


@dataclass(frozen=True)
class Outgoing:
    entity_type: EntityType
    entity_id: UUID
    kind: Kind
    token: str
    text: str
    markup: messages.Keyboard
    chats: tuple[int, ...]


@dataclass(frozen=True)
class _Edit:
    chat_id: int
    message_id: int
    text: str


class Outbox:
    def __init__(self, ctx: BotContext) -> None:
        self._ctx = ctx
        self._paused_chats: dict[int, float] = {}

    def scan(self) -> int:
        """One scan; returns the number of messages sent. Raises on database errors and on
        Telegram rate limiting (429), which the runner turns into a backoff."""
        with self._ctx.open_conn() as conn:
            store.delete_stale_claims(conn)
            store.delete_expired_replies(conn)
            with conn.transaction():
                retired = self._retire_outdated(conn)
            outgoing = self._collect(conn)
        for edit in retired:
            best_effort(
                "retiring an outdated message",
                partial(
                    self._ctx.client.edit_message_text, edit.chat_id, edit.message_id, edit.text
                ),
            )
        sent = 0
        for item in outgoing:
            for chat_id in item.chats:
                if self._send(item, chat_id):
                    sent += 1
                    if self._ctx.sleep(SEND_PACING_S):
                        return sent
        return sent

    # --- retire ------------------------------------------------------------------------

    def _retire_outdated(self, conn: Conn) -> list[_Edit]:
        """Resolve live messages whose entity changed since they were sent (decided in the
        admin UI, edited, deleted) and return the edits that remove their buttons."""
        edits: list[_Edit] = []
        stale: list[UUID] = []
        for row in store.unresolved_with_state(conn):
            kind: Kind = row["kind"]
            is_event = row["entity_type"] == "event"
            status = row["event_status"] if is_event else row["application_status"]
            token = current_token(kind, status, row["updated_at"])
            if token == row["state_token"]:
                continue
            stale.append(row["id"])
            if status is None:
                head, outcome = "<b>Deleted entry</b>", "It no longer exists."
            else:
                head = (
                    messages.event_header(row)
                    if is_event
                    else messages.application_header(row["entity_type"], row)
                )
                outcome = (
                    "Changed since this message; an updated message follows."
                    if token is not None
                    else f"Now <i>{escape_html(status)}</i>; nothing to do here."
                )
            edits.append(
                _Edit(row["chat_id"], row["message_id"], messages.outcome_text(head, outcome))
            )
        store.resolve_ids(conn, stale, "superseded")
        return edits

    # --- collect -----------------------------------------------------------------------

    def _collect(self, conn: Conn) -> list[Outgoing]:
        items: list[Outgoing] = []
        event_kinds: tuple[Kind, ...] = ("review", "publish")
        for kind in event_kinds:
            events = store.events_in_status(conn, KIND_STATUS[kind], MAX_ENTITIES_PER_KIND)
            items += self._missing(conn, kind, "event", events)
        for entity_type in ("community_application", "team_application"):
            rows = store.new_applications(conn, entity_type, MAX_ENTITIES_PER_KIND)
            items += self._missing(conn, "application", entity_type, rows)
        return items

    def _missing(
        self, conn: Conn, kind: Kind, entity_type: EntityType, rows: list[Any]
    ) -> list[Outgoing]:
        if not rows:
            return []
        live = store.live_slots(conn, kind, [row["id"] for row in rows])
        now = time.monotonic()
        admins = sorted(
            chat for chat in self._ctx.config.admin_ids if self._paused_chats.get(chat, 0) <= now
        )
        items = []
        for row in rows:
            status = row["status"]
            token = current_token(kind, status, row.get("updated_at"))
            if token is None:  # pragma: no cover - rows were selected by status
                continue
            chats = tuple(chat for chat in admins if (row["id"], token, chat) not in live)
            if not chats:
                continue
            items.append(
                Outgoing(
                    entity_type=entity_type,
                    entity_id=row["id"],
                    kind=kind,
                    token=token,
                    text=self._text(conn, kind, entity_type, row),
                    markup=messages.keyboard(kind, entity_type, row["id"], token),
                    chats=chats,
                )
            )
        return items

    def _text(self, conn: Conn, kind: Kind, entity_type: EntityType, row: Mapping[str, Any]) -> str:
        if kind == "application":
            return messages.application_text(entity_type, row)
        if kind == "publish":
            return messages.publish_text(row)
        # Deterministic signals as on the review screen, without the network URL check.
        candidates = events_repository.find_duplicate_candidates(
            conn, row["id"], row["official_url_normalized"], row["start_date"]
        )
        signals = compute_signals(
            row,
            url_check=None,
            duplicates=find_duplicates(row, candidates),
            sources_by_tier=count_by_tier(sources_repository.list_event_sources(conn, row["id"])),
        )
        return messages.review_text(row, signals)

    # --- send --------------------------------------------------------------------------

    def _send(self, item: Outgoing, chat_id: int) -> bool:
        with self._ctx.open_conn() as conn:
            claim_id = store.claim(
                conn, item.entity_type, item.entity_id, item.kind, item.token, chat_id
            )
        if claim_id is None:
            return False
        error: TelegramError | None = None
        try:
            message = self._ctx.client.send_message(chat_id, item.text, reply_markup=item.markup)
        except TelegramError as exc:
            error = exc
        if error is not None:
            with self._ctx.open_conn() as conn:
                store.release_claim(conn, claim_id)
            if isinstance(error, TelegramAPIError):
                if error.retry_after is not None:
                    raise error  # rate limited: the runner backs off
                if error.error_code == 403:
                    self._paused_chats[chat_id] = time.monotonic() + BLOCKED_CHAT_PAUSE_S
            logger.warning("admin bot: sending a %s notification failed: %s", item.kind, error)
            return False
        with self._ctx.open_conn() as conn:
            store.mark_sent(conn, claim_id, message.message_id)
        return True

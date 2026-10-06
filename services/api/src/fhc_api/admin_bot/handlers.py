"""Button presses and reason replies.

Order for every update: allowlist (numeric user id, private chat with that user) →
the message must be a live notification of this bot → press age → state token against
the entity as it is now (row locked) → action through the existing services (same
guards, notes, timestamps and audit as the admin UI). The database work commits first;
Telegram calls (answers, edits, prompts) and web revalidation run afterwards, outside
the connection, and are best effort.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from typing import Any, cast
from uuid import UUID

from fastapi import HTTPException

from fhc_api.admin_bot import messages, store
from fhc_api.admin_bot.codec import KIND_ACTIONS, Action, Callback, Kind, decode
from fhc_api.admin_bot.context import BotContext, best_effort, current_token, logger
from fhc_api.common.audit import telegram_actor
from fhc_api.community import service as community_service
from fhc_api.community.models import ApplicationStatus
from fhc_api.community.repository import ApplicationTable
from fhc_api.db import Conn
from fhc_api.events import service as events_service
from fhc_api.events.models import EventAction, EventTransition
from fhc_api.telegram.client import (
    TelegramCallbackQuery,
    TelegramError,
    TelegramMessage,
    TelegramUpdate,
)
from fhc_api.telegram.formatting import escape_html
from fhc_api.web.revalidate import event_tags

REASON_TTL_MINUTES = 15
REASON_MAX_LENGTH = 1000  # EventTransition.reason

# Button -> (event transition, notification resolution, outcome line)
_EVENT_ACTIONS: dict[Action, tuple[EventAction, str, str]] = {
    "approve": ("approve", "approved", "✅ Approved"),
    "publish_confirm": ("publish", "published", "🚀 Published"),
    "reject_confirm": ("reject", "rejected", "⛔ Rejected"),
    "request_changes": ("request_changes", "changes_requested", "✏️ Changes requested (draft)"),
}
_APPLICATION_STATUSES: dict[Action, ApplicationStatus] = {
    "contacted": "contacted",
    "accepted": "accepted",
    "declined": "declined",
    "spam": "spam",
}
_APPLICATION_TABLES: dict[str, ApplicationTable] = {
    "community_application": "community_applications",
    "team_application": "team_applications",
}
_REASON_ACTIONS: frozenset[Action] = frozenset({"request_changes", "reject_confirm"})


@dataclass(frozen=True)
class _Prompt:
    chat_id: int
    reply_to: int
    notification_id: UUID
    entity_id: UUID
    action: Action
    token: str
    head: str


@dataclass
class _Effects:
    """Telegram side effects of one update, applied after the database commit."""

    answer: str | None = None  # plain text (callback answer, or a chat message for replies)
    edits: list[tuple[int, int, str]] = field(default_factory=list)  # text, no buttons
    markup: tuple[int, int, messages.Keyboard] | None = None  # replace buttons
    prompt: _Prompt | None = None
    revalidate_slug: str | None = None
    scan: bool = False


class Handlers:
    def __init__(self, ctx: BotContext) -> None:
        self._ctx = ctx

    def handle(self, update: TelegramUpdate) -> None:
        """Database availability errors propagate (the runner retries the update later);
        anything else is logged and the update is considered handled."""
        if update.callback_query is not None:
            self._on_callback(update.callback_query)
        elif update.message is not None:
            self._on_message(update.message)

    # --- presses -----------------------------------------------------------------------

    def _on_callback(self, query: TelegramCallbackQuery) -> None:
        user_id = query.from_.id
        if user_id not in self._ctx.config.admin_ids:
            logger.warning("admin bot: ignored a button press from a user not on the allowlist")
            self._answer(query.id, "Not allowed.")
            return
        message = query.message
        if message is None or message.chat.type != "private" or message.chat.id != user_id:
            self._answer(query.id, "Not available here.")
            return
        callback = decode(query.data)
        if callback is None:
            self._answer(query.id, "Unknown button.")
            return
        with self._ctx.open_conn() as conn, conn.transaction():
            effects = self._press(conn, callback, message.chat.id, message.message_id, user_id)
        self._apply(effects, callback_query_id=query.id)

    def _press(
        self, conn: Conn, callback: Callback, chat_id: int, message_id: int, user_id: int
    ) -> _Effects:
        here = (chat_id, message_id)
        note = store.find_by_message(conn, chat_id, message_id, self._ctx.config.max_press_age_h)
        if (
            note is None
            or note["message_id"] is None
            or (note["entity_type"], note["entity_id"])
            != (callback.entity_type, callback.entity_id)
            or callback.action not in KIND_ACTIONS[note["kind"]]
        ):
            return _Effects(answer="This message is not active any more.", markup=(*here, {}))
        if callback.token != note["state_token"]:
            # Not a button this bot put on this message; leave the message as it is.
            return _Effects(answer="Unknown button.")
        if note["resolved_at"] is not None:
            return _Effects(answer=f"Already handled ({note['resolution']}).")
        entity = store.load_entity(conn, callback.entity_type, callback.entity_id, for_update=True)
        head = (
            messages.header(callback.entity_type, entity)
            if entity is not None
            else "<b>Deleted entry</b>"
        )
        if note["expired"]:
            store.resolve_ids(conn, [note["id"]], "expired")
            hours = f"{self._ctx.config.max_press_age_h:g}"
            return _Effects(
                answer="These buttons expired. A fresh message follows if still needed.",
                edits=[
                    (*here, messages.outcome_text(head, f"⌛ Buttons expired after {hours} h."))
                ],
                scan=True,
            )
        status = None if entity is None else str(entity["status"])
        token = current_token(
            note["kind"], status, None if entity is None else entity.get("updated_at")
        )
        if token != note["state_token"]:
            store.resolve_ids(conn, [note["id"]], "superseded")
            now = f"now <i>{escape_html(status)}</i>" if status else "it no longer exists"
            return _Effects(
                answer="Outdated: this changed since the message was sent.",
                edits=[(*here, messages.outcome_text(head, f"Outdated: {now}."))],
                scan=True,
            )
        return self._dispatch(conn, callback, note, head, user_id)

    def _dispatch(
        self, conn: Conn, callback: Callback, note: dict[str, Any], head: str, user_id: int
    ) -> _Effects:
        here = (note["chat_id"], note["message_id"])
        action, kind = callback.action, cast(Kind, note["kind"])
        keyboard_args = (callback.entity_type, callback.entity_id, callback.token)
        if action == "reject":
            return _Effects(
                answer="Confirm to reject (a reason follows).",
                markup=(*here, messages.keyboard("reject_confirm", *keyboard_args)),
            )
        if action == "publish":
            return _Effects(
                answer="Confirm to publish on the public site.",
                markup=(*here, messages.keyboard("publish_confirm", *keyboard_args)),
            )
        if action == "cancel":
            return _Effects(
                answer="Cancelled.", markup=(*here, messages.keyboard(kind, *keyboard_args))
            )
        if action in _REASON_ACTIONS:
            return _Effects(
                answer="Reply to the prompt with the reason.",
                markup=(*here, messages.keyboard(kind, *keyboard_args)),
                prompt=_Prompt(
                    chat_id=note["chat_id"],
                    reply_to=note["message_id"],
                    notification_id=note["id"],
                    entity_id=callback.entity_id,
                    action=action,
                    token=callback.token,
                    head=head,
                ),
            )
        if action == "later":
            store.resolve_ids(conn, [note["id"]], "later")
            return _Effects(
                answer="Left for later.",
                edits=[(*here, messages.outcome_text(head, "Later: publish from the admin UI."))],
            )
        actor = telegram_actor(user_id)
        if action in _APPLICATION_STATUSES:
            status = _APPLICATION_STATUSES[action]
            try:
                community_service.set_status(
                    conn,
                    _APPLICATION_TABLES[callback.entity_type],
                    callback.entity_id,
                    status,
                    actor=actor,
                )
            except HTTPException as exc:
                return _Effects(answer=str(exc.detail))
            targets = store.resolve_entity(
                conn, callback.entity_type, callback.entity_id, kind, status
            )
            return self._decided(head, f"Marked {status}", actor, targets)
        return self._transition(conn, note, head, action, None, actor)

    def _transition(
        self,
        conn: Conn,
        note: dict[str, Any],
        head: str,
        action: Action,
        reason: str | None,
        actor: str,
    ) -> _Effects:
        event_action, resolution, label = _EVENT_ACTIONS[action]
        try:
            result = events_service.transition_event(
                conn,
                note["entity_id"],
                EventTransition(action=event_action, reason=reason),
                actor=actor,
            )
        except HTTPException as exc:  # 404/409/422: the savepoint rolled back, nothing changed
            return _Effects(answer=f"Not done: {exc.detail}")
        targets = store.resolve_entity(conn, "event", note["entity_id"], note["kind"], resolution)
        effects = self._decided(head, label, actor, targets)
        if result.affects_public_site:
            effects.revalidate_slug = result.row["slug"]
        return effects

    @staticmethod
    def _decided(head: str, label: str, actor: str, targets: list[Any]) -> _Effects:
        text = messages.outcome_text(head, f"{label} by {escape_html(actor)}", datetime.now(UTC))
        return _Effects(
            answer=label,
            edits=[(row["chat_id"], row["message_id"], text) for row in targets],
            scan=True,
        )

    # --- messages and reason replies ---------------------------------------------------

    def _on_message(self, message: TelegramMessage) -> None:
        user = message.from_
        if user is None or user.id not in self._ctx.config.admin_ids or message.chat.id != user.id:
            logger.warning("admin bot: ignored a message from a user or chat not on the allowlist")
            return
        if message.chat.type != "private":  # pragma: no cover - chat id == user id is private
            return
        if message.reply_to_message is not None:
            with self._ctx.open_conn() as conn, conn.transaction():
                effects = self._reason(conn, message, message.reply_to_message.message_id, user.id)
            if effects is not None:
                self._apply(effects, reply_chat=message.chat.id)
                return
        self._send(message.chat.id, messages.HELP_TEXT)

    def _reason(
        self, conn: Conn, message: TelegramMessage, prompt_id: int, user_id: int
    ) -> _Effects | None:
        pending = store.get_pending_reply(conn, message.chat.id, prompt_id)
        if pending is None:
            return None
        if pending["expired"]:
            store.delete_pending_reply(conn, pending["id"])
            return _Effects(answer="That prompt expired. Press the button again.")
        reason = " ".join((message.text or "").split())
        if not reason or len(reason) > REASON_MAX_LENGTH:
            # The prompt stays open: the admin can reply again.
            return _Effects(
                answer=f"Please reply with a text reason of 1-{REASON_MAX_LENGTH} characters."
            )
        store.delete_pending_reply(conn, pending["id"])
        note = store.get_notification(conn, pending["notification_id"])
        if note is None or note["resolved_at"] is not None:
            return _Effects(answer="Already handled.")
        entity = store.load_entity(conn, "event", pending["entity_id"], for_update=True)
        head = messages.event_header(entity) if entity is not None else "<b>Deleted entry</b>"
        status = None if entity is None else str(entity["status"])
        token = current_token(
            note["kind"], status, None if entity is None else entity["updated_at"]
        )
        if token != pending["state_token"]:
            store.resolve_ids(conn, [note["id"]], "superseded")
            return _Effects(
                answer="Outdated: the event changed since the prompt. Nothing was done.",
                edits=[
                    (note["chat_id"], note["message_id"], messages.outcome_text(head, "Outdated."))
                ],
                scan=True,
            )
        action: Action = "reject_confirm" if pending["action"] == "reject" else "request_changes"
        return self._transition(conn, note, head, action, reason, telegram_actor(user_id))

    # --- side effects ------------------------------------------------------------------

    def _apply(
        self,
        effects: _Effects,
        *,
        callback_query_id: str | None = None,
        reply_chat: int | None = None,
    ) -> None:
        answer = effects.answer
        if effects.prompt is not None and not self._ask_reason(effects.prompt):
            answer = "Could not send the reason prompt; try again."
        if callback_query_id is not None:
            self._answer(callback_query_id, answer)
        elif reply_chat is not None and answer:
            self._send(reply_chat, escape_html(answer))
        client = self._ctx.client
        if effects.markup is not None:
            chat_id, message_id, markup = effects.markup
            best_effort(
                "updating buttons",
                lambda: client.edit_message_reply_markup(chat_id, message_id, markup or None),
            )
        for chat_id, message_id, text in effects.edits:
            best_effort(
                "editing a message",
                partial(client.edit_message_text, chat_id, message_id, text),
            )
        if effects.revalidate_slug is not None:
            # Best effort and never raises (WebRevalidator logs failures).
            self._ctx.revalidator.revalidate(event_tags(effects.revalidate_slug))
        if effects.scan:
            self._ctx.request_scan()

    def _ask_reason(self, prompt: _Prompt) -> bool:
        text = messages.reason_prompt_text(prompt.action, prompt.head, REASON_TTL_MINUTES)
        try:
            sent = self._ctx.client.send_message(
                prompt.chat_id,
                text,
                reply_markup=messages.FORCE_REPLY,
                reply_to_message_id=prompt.reply_to,
            )
        except TelegramError as exc:
            logger.warning("admin bot: sending a reason prompt failed: %s", exc)
            return False
        with self._ctx.open_conn() as conn:
            store.add_pending_reply(
                conn,
                chat_id=prompt.chat_id,
                prompt_message_id=sent.message_id,
                notification_id=prompt.notification_id,
                entity_id=prompt.entity_id,
                action="reject" if prompt.action == "reject_confirm" else "request_changes",
                token=prompt.token,
                ttl_minutes=REASON_TTL_MINUTES,
            )
        return True

    def _answer(self, callback_query_id: str, text: str | None) -> None:
        best_effort(
            "answering a button press",
            lambda: self._ctx.client.answer_callback_query(callback_query_id, text),
        )

    def _send(self, chat_id: int, text: str) -> None:
        best_effort("sending a reply", lambda: self._ctx.client.send_message(chat_id, text))

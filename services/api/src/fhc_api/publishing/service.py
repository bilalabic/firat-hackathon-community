"""Telegram channel publishing (V1.1a): preview, send, update and delete one post per event.

Used by the admin API (`publishing/router.py`) and the admin bot ("Post to channel").

- The post is a `sendPhoto` with the public event card
  (`WEB_BASE_URL/hackathonlar/<slug>/opengraph-image?v=<card hash>`, D-14) and the caption
  from `caption.py`. The `?v=` part changes when the card changes, so Telegram fetches the
  new image instead of reusing the one it downloaded for the old URL.
- When Telegram cannot use the card (it could not fetch or process the URL), the post is
  sent as a text message with a link preview of the detail page; the row records it
  (`message_type = 'text'`, the reason in `error`).
- Only `published` events are posted (the card exists only for published events). One
  draft or live post per event: the event row is locked while the post is claimed, and a
  unique index backs it up. A post is claimed as `draft` *before* the Bot API call and
  becomes `sent` or `failed` afterwards; no database connection is held during the call.
- Unpublishing or archiving never deletes a post automatically: the preview reports
  `not_public` and offers Delete.
- Every operation writes one `app.admin_actions` row (outcome only, no text).

Error texts come from `TelegramError` messages (never the token) or are fixed sentences.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from psycopg.rows import DictRow

from fhc_api.common import audit
from fhc_api.common.errors import bad_gateway, conflict, not_found
from fhc_api.config import Settings
from fhc_api.db import Conn, ConnFactory
from fhc_api.events import repository as events_repository
from fhc_api.publishing import repository
from fhc_api.publishing.caption import Caption, build_caption
from fhc_api.publishing.hashing import card_hash, publishable_hash
from fhc_api.publishing.models import (
    ActionOutcome,
    AuditEntry,
    ChannelActionOut,
    ChannelHistory,
    ChannelPostPage,
    ChannelPostSummary,
    ChannelPreview,
    PostState,
    PublicationOut,
)
from fhc_api.telegram.client import (
    TelegramAPIError,
    TelegramClient,
    TelegramError,
    TelegramMessage,
    TelegramNetworkError,
)

CARD_VERSION_LENGTH = 16
INTERRUPTED = (
    "Sending was interrupted (the API stopped, or the result could not be saved). "
    "The message may exist in the channel: check it before sending again."
)
CHANGED_SINCE_PREVIEW = (
    "the event changed since the preview; check the new preview and confirm again"
)
# Bot API error descriptions (400) that mean Telegram could not use the photo URL. The docs
# list no codes or texts; these are the descriptions Telegram returns in practice
# ("wrong file identifier/HTTP URL specified", "failed to get HTTP URL content", "wrong type
# of the web page content", "PHOTO_INVALID_DIMENSIONS", "IMAGE_PROCESS_FAILED").
_PHOTO_ERROR_HINTS = ("url", "file", "photo", "image", "web page content", "dimensions")


@dataclass(frozen=True)
class Rendered:
    caption: Caption
    content_hash: str
    detail_url: str | None
    image_url: str | None


def is_photo_error(exc: TelegramError) -> bool:
    if not isinstance(exc, TelegramAPIError) or exc.error_code != 400:
        return False
    description = exc.description.lower()
    if "chat not found" in description or "parse entities" in description:
        return False
    return any(hint in description for hint in _PHOTO_ERROR_HINTS)


def _not_found_in_channel(exc: TelegramError) -> bool:
    """`message to edit not found` / `message to delete not found` (400)."""
    return (
        isinstance(exc, TelegramAPIError)
        and exc.error_code == 400
        and "message to" in exc.description.lower()
        and "not found" in exc.description.lower()
    )


def _not_modified(exc: TelegramError) -> bool:
    return isinstance(exc, TelegramAPIError) and "message is not modified" in exc.description


def describe_error(exc: TelegramError, *, sending: bool = False) -> str:
    """An operator-facing sentence. Telegram's own text is kept where it helps; it never
    contains the token (TelegramClient redacts and never chains HTTP objects)."""
    if isinstance(exc, TelegramAPIError):
        code, description = exc.error_code, exc.description
        low = description.lower()
        if code == 401 or (code == 404 and low.strip() == "not found"):
            return "Telegram rejected the channel bot token. Check TELEGRAM_BOT_TOKEN."
        if code == 403 or "not enough rights" in low or "administrator" in low:
            return (
                "The bot cannot post or edit in the channel: it is not an administrator or "
                "lacks a right (run Settings → Telegram check)."
            )
        if "chat not found" in low:
            return "Telegram cannot find the channel. Check TELEGRAM_CHANNEL_ID."
        if exc.retry_after is not None:
            return f"Telegram rate limit: retry after {exc.retry_after} s."
        if "can't be deleted" in low:
            return (
                f"Telegram refused to delete the post ({description}). Bots may delete channel "
                "posts only within 48 hours unless they have the Delete messages right; this "
                "is not verified yet (TELEGRAM_RESEARCH T-1). Delete it in the channel by "
                "hand, then press Delete again to mark it deleted here."
            )
        return f"Telegram refused the request ({code}: {description})."
    if isinstance(exc, TelegramNetworkError) and sending:
        return (
            f"{exc} The post may have been published anyway: check the channel before "
            "sending again."
        )
    return str(exc)


def _chat(target: str) -> int | str:
    """Stored targets are numeric chat ids (from the sent message); `@name` stays a string."""
    try:
        return int(target)
    except ValueError:
        return target


def _out(row: Mapping[str, Any] | None) -> PublicationOut | None:
    return None if row is None else PublicationOut.model_validate(dict(row))


class ChannelPublisher:
    def __init__(
        self,
        settings: Settings,
        client: TelegramClient | None,
        *,
        invalid_token_format: bool = False,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._channel = (settings.TELEGRAM_CHANNEL_ID or "").strip() or None
        base = settings.WEB_BASE_URL
        self._web_base = str(base).rstrip("/") if base is not None else None
        self._now = now
        if invalid_token_format:
            self.config_problem: str | None = "TELEGRAM_BOT_TOKEN has an invalid format."
        elif client is None or self._channel is None:
            self.config_problem = (
                "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID in services/api/.env."
            )
        elif self._web_base is None:
            self.config_problem = (
                "Set WEB_BASE_URL (the public site) in services/api/.env: posts link to the "
                "event page and use its card image."
            )
        elif not self._web_base.startswith("https://"):
            self.config_problem = (
                "WEB_BASE_URL must be an https URL of the public site: Telegram downloads "
                "the event card from it."
            )
        else:
            self.config_problem = None

    @property
    def configured(self) -> bool:
        return self.config_problem is None

    # --- rendering ---------------------------------------------------------------------

    def render(self, event: Mapping[str, Any]) -> Rendered:
        detail_url = image_url = None
        if self._web_base is not None:
            detail_url = f"{self._web_base}/hackathonlar/{event['slug']}"
            version = card_hash(event)[:CARD_VERSION_LENGTH]
            image_url = f"{detail_url}/opengraph-image?v={version}"
        return Rendered(
            caption=build_caption(event, detail_url=detail_url),
            content_hash=publishable_hash(event),
            detail_url=detail_url,
            image_url=image_url,
        )

    @staticmethod
    def card_changed(post: Mapping[str, Any] | None, rendered: Rendered) -> bool:
        return (
            post is not None
            and post["message_type"] == "photo"
            and post["image_url"] != rendered.image_url
        )

    def post_state(
        self, event: Mapping[str, Any], post: Mapping[str, Any] | None, rendered: Rendered
    ) -> PostState:
        if post is None or post["stale"]:
            return "not_posted"
        if post["status"] == "draft":
            return "sending"
        if event["status"] != "published":
            return "not_public"
        if (
            post["content_hash"] != rendered.content_hash
            or post["body"] != rendered.caption.html
            or self.card_changed(post, rendered)
        ):
            return "changed"
        return "posted"

    # --- reads -------------------------------------------------------------------------

    def preview(self, conn: Conn, event_id: UUID) -> ChannelPreview:
        event = events_repository.get(conn, event_id)
        if event is None:
            raise not_found("event")
        post = repository.live_post(conn, event_id)
        return self._preview(event, post)

    def _preview(self, event: Mapping[str, Any], post: Mapping[str, Any] | None) -> ChannelPreview:
        rendered = self.render(event)
        state = self.post_state(event, post, rendered)
        published = event["status"] == "published"
        live = post is not None and post["status"] in ("sent", "edited")
        return ChannelPreview(
            event_id=event["id"],
            slug=event["slug"],
            title=event["title"],
            event_status=event["status"],
            configured=self.configured,
            config_problem=self.config_problem,
            caption_html=rendered.caption.html,
            caption_text=rendered.caption.text,
            caption_length=rendered.caption.length,
            caption_truncated=rendered.caption.truncated,
            image_url=rendered.image_url,
            detail_url=rendered.detail_url,
            content_hash=rendered.content_hash,
            post_state=state,
            card_changed=self.card_changed(post, rendered),
            current_post=_out(post),
            can_send=self.configured and published and state == "not_posted",
            can_update=self.configured and published and state == "changed",
            can_delete=self._client is not None and live,
        )

    def list_posts(self, conn: Conn, *, limit: int, offset: int) -> ChannelPostPage:
        events, total = repository.page_of_events(conn, limit=limit, offset=offset)
        posts = repository.live_posts(conn, [event["id"] for event in events])
        items = []
        for event in events:
            post = posts.get(event["id"])
            items.append(
                ChannelPostSummary(
                    event_id=event["id"],
                    slug=event["slug"],
                    title=event["title"],
                    event_status=event["status"],
                    start_date=event["start_date"],
                    post_state=self.post_state(event, post, self.render(event)),
                    current_post=_out(post),
                )
            )
        return ChannelPostPage(items=items, total=total, limit=limit, offset=offset)

    def history(self, conn: Conn, event_id: UUID) -> ChannelHistory:
        if events_repository.get(conn, event_id) is None:
            raise not_found("event")
        return ChannelHistory(
            posts=[
                PublicationOut.model_validate(dict(row))
                for row in repository.history(conn, event_id)
            ],
            actions=[
                AuditEntry.model_validate(dict(row))
                for row in repository.audit_entries(conn, event_id)
            ],
        )

    # --- writes ------------------------------------------------------------------------

    def _require_client(self) -> TelegramClient:
        if self._client is None:
            raise conflict(self.config_problem or "Telegram is not configured")
        return self._client

    def _lock_publishable(
        self, conn: Conn, event_id: UUID, expected_hash: str | None, action: str
    ) -> tuple[DictRow, Rendered]:
        if self.config_problem is not None:
            raise conflict(f"channel publishing is not configured: {self.config_problem}")
        event = events_repository.get(conn, event_id, for_update=True)
        if event is None:
            raise not_found("event")
        if event["status"] != "published":
            raise conflict(
                f"cannot {action}: the event is {event['status']}; only published events "
                "are posted (delete an existing post instead)"
            )
        rendered = self.render(event)
        if expected_hash is not None and expected_hash != rendered.content_hash:
            raise conflict(CHANGED_SINCE_PREVIEW)
        return event, rendered

    def _record(
        self,
        conn: Conn,
        *,
        actor: str,
        action: str,
        post_id: UUID,
        event_id: UUID,
        values: dict[str, Any],
        outcome: str,
    ) -> DictRow:
        row = repository.update(conn, post_id, values)
        audit.record(
            conn,
            actor=actor,
            action=action,
            entity_type="event",
            entity_id=event_id,
            detail={
                "publication_id": str(post_id),
                "content_version": row["content_version"],
                "outcome": outcome,
            },
        )
        return row

    def send(
        self, open_conn: ConnFactory, event_id: UUID, *, actor: str, expected_hash: str | None
    ) -> ChannelActionOut:
        client = self._require_client()
        with open_conn() as conn, conn.transaction():
            _, rendered = self._lock_publishable(conn, event_id, expected_hash, "post")
            post = repository.live_post(conn, event_id, for_update=True)
            if post is not None:
                if not post["stale"]:
                    raise conflict(
                        "a post for this event is being sent"
                        if post["status"] == "draft"
                        else "the event is already posted; update or delete that post"
                    )
                repository.update(conn, post["id"], {"status": "failed", "error": INTERRUPTED})
            claim = repository.insert(
                conn,
                {
                    "event_id": event_id,
                    "target": self._channel,
                    "content_hash": rendered.content_hash,
                    "body": rendered.caption.html,
                    "image_url": rendered.image_url,
                    "status": "draft",
                },
            )

        message, message_type, note, error = self._post(client, rendered)

        with open_conn() as conn, conn.transaction():
            if error is not None:
                row = self._record(
                    conn,
                    actor=actor,
                    action="telegram_post",
                    post_id=claim["id"],
                    event_id=event_id,
                    values={"status": "failed", "error": describe_error(error, sending=True)},
                    outcome="failed",
                )
            else:
                assert message is not None  # noqa: S101 - set whenever error is None
                outcome: ActionOutcome = "sent" if message_type == "photo" else "sent_as_text"
                row = self._record(
                    conn,
                    actor=actor,
                    action="telegram_post",
                    post_id=claim["id"],
                    event_id=event_id,
                    values={
                        "status": "sent",
                        "external_id": str(message.message_id),
                        "target": str(message.chat.id),
                        "sent_at": self._now(),
                        "message_type": message_type,
                        "image_url": rendered.image_url if message_type == "photo" else None,
                        "error": note,
                    },
                    outcome=outcome,
                )
        if error is not None:
            raise bad_gateway(row["error"])
        text = "Posted to the channel." if outcome == "sent" else f"Posted as text. {note}"
        return ChannelActionOut(
            outcome=outcome, message=text, publication=PublicationOut.model_validate(dict(row))
        )

    def _post(
        self, client: TelegramClient, rendered: Rendered
    ) -> tuple[TelegramMessage | None, str, str | None, TelegramError | None]:
        """(message, message type, fallback note, error)."""
        assert self._channel is not None and rendered.image_url is not None  # noqa: S101
        chat = _chat(self._channel)
        try:
            return (
                client.send_photo(chat, rendered.image_url, caption=rendered.caption.html),
                "photo",
                None,
                None,
            )
        except TelegramError as exc:
            if not is_photo_error(exc):
                return None, "photo", None, exc
            note = (
                f"Telegram could not use the event card ({exc}); sent as text with a link "
                "preview of the event page."
            )
        try:
            message = client.send_message(
                chat, rendered.caption.html, link_preview_options=self._link_preview(rendered)
            )
        except TelegramError as exc:
            return None, "text", None, exc
        return message, "text", note, None

    @staticmethod
    def _link_preview(rendered: Rendered) -> dict[str, Any]:
        return {"url": rendered.detail_url, "prefer_large_media": True, "show_above_text": True}

    def update(
        self, open_conn: ConnFactory, event_id: UUID, *, actor: str, expected_hash: str | None
    ) -> ChannelActionOut:
        client = self._require_client()
        with open_conn() as conn, conn.transaction():
            _, rendered = self._lock_publishable(conn, event_id, expected_hash, "update the post")
            post = repository.live_post(conn, event_id, for_update=True)
            if post is None or post["stale"] or post["status"] == "draft":
                raise conflict(
                    "a post for this event is being sent"
                    if post is not None and not post["stale"]
                    else "the event is not posted; send it first"
                )
            if self.post_state({"status": "published"}, post, rendered) == "posted":
                return ChannelActionOut(
                    outcome="unchanged",
                    message="The post is already up to date.",
                    publication=PublicationOut.model_validate(dict(post)),
                )

        outcome, message_type, image_url, note, error = self._edit(client, post, rendered)
        gone = error is not None and _not_found_in_channel(error)

        with open_conn() as conn, conn.transaction():
            current = repository.get(conn, post["id"], for_update=True)
            assert current is not None  # noqa: S101 - publications are never deleted
            if gone:
                row = self._record(
                    conn,
                    actor=actor,
                    action="telegram_update",
                    post_id=post["id"],
                    event_id=event_id,
                    values={
                        "status": "deleted",
                        "deleted_at": self._now(),
                        "error": "The message no longer exists in the channel.",
                    },
                    outcome="already_gone",
                )
            elif error is not None:
                row = self._record(
                    conn,
                    actor=actor,
                    action="telegram_update",
                    post_id=post["id"],
                    event_id=event_id,
                    values={"error": describe_error(error)},
                    outcome="failed",
                )
            else:
                row = self._record(
                    conn,
                    actor=actor,
                    action="telegram_update",
                    post_id=post["id"],
                    event_id=event_id,
                    values={
                        "status": "edited",
                        "edited_at": self._now(),
                        "content_version": current["content_version"] + 1,
                        "content_hash": rendered.content_hash,
                        "body": rendered.caption.html,
                        "image_url": image_url,
                        "message_type": message_type,
                        "error": note,
                    },
                    outcome=outcome,
                )
        if error is not None:
            if gone:
                raise conflict(
                    "the post no longer exists in the channel (deleted there?); it is marked "
                    "deleted, so a new post can be sent"
                )
            raise bad_gateway(row["error"])
        text = (
            "Post updated."
            if outcome == "edited"
            else f"Caption updated; the card was not replaced. {note}"
        )
        return ChannelActionOut(
            outcome=outcome, message=text, publication=PublicationOut.model_validate(dict(row))
        )

    def _edit(
        self, client: TelegramClient, post: Mapping[str, Any], rendered: Rendered
    ) -> tuple[ActionOutcome, str, str | None, str | None, TelegramError | None]:
        """(outcome, message type, image url, note, error). A text post (card fallback) is
        turned into a photo post when the card works now; a photo post gets a new photo
        only when the card changed."""
        assert rendered.image_url is not None  # noqa: S101 - configured
        chat, message_id = _chat(post["target"]), int(post["external_id"])
        caption = rendered.caption.html
        is_text = post["message_type"] == "text"
        try:
            if is_text or self.card_changed(post, rendered):
                try:
                    client.edit_message_media(chat, message_id, rendered.image_url, caption=caption)
                    return "edited", "photo", rendered.image_url, None, None
                except TelegramError as exc:
                    if not is_photo_error(exc):
                        raise
                    note = f"Telegram could not use the new event card ({exc})."
                if is_text:
                    client.edit_message_text(
                        chat, message_id, caption, link_preview_options=self._link_preview(rendered)
                    )
                    return "edited", "text", None, note, None
                client.edit_message_caption(chat, message_id, caption)
                return "edited_caption_only", "photo", post["image_url"], note, None
            client.edit_message_caption(chat, message_id, caption)
        except TelegramError as exc:
            if not _not_modified(exc):
                return "edited", post["message_type"], post["image_url"], None, exc
        return "edited", post["message_type"], post["image_url"], None, None

    def delete(
        self, open_conn: ConnFactory, event_id: UUID, publication_id: UUID, *, actor: str
    ) -> ChannelActionOut:
        """Allowed whatever the event status (also after unpublish/archive)."""
        client = self._require_client()
        with open_conn() as conn:
            post = repository.get(conn, publication_id)
        if post is None or post["event_id"] != event_id:
            raise not_found("post")
        if post["status"] not in ("sent", "edited"):
            raise conflict(f"cannot delete a post in status {post['status']}")

        error: TelegramError | None = None
        outcome: ActionOutcome = "deleted"
        try:
            client.delete_message(_chat(post["target"]), int(post["external_id"]))
        except TelegramError as exc:
            if _not_found_in_channel(exc):
                outcome = "already_gone"
            else:
                error = exc

        with open_conn() as conn, conn.transaction():
            current = repository.get(conn, publication_id, for_update=True)
            if current is None or current["status"] not in ("sent", "edited"):
                raise conflict("the post changed while it was being deleted; reload the page")
            if error is not None:
                values: dict[str, Any] = {"error": describe_error(error)}
            else:
                note = (
                    "The message no longer existed in the channel."
                    if outcome == "already_gone"
                    else None
                )
                values = {"status": "deleted", "deleted_at": self._now(), "error": note}
            row = self._record(
                conn,
                actor=actor,
                action="telegram_delete",
                post_id=publication_id,
                event_id=event_id,
                values=values,
                outcome="failed" if error is not None else outcome,
            )
        if error is not None:
            raise bad_gateway(row["error"])
        text = (
            "Post deleted from the channel."
            if outcome == "deleted"
            else "The message was already gone from the channel; it is marked deleted."
        )
        return ChannelActionOut(
            outcome=outcome, message=text, publication=PublicationOut.model_validate(dict(row))
        )

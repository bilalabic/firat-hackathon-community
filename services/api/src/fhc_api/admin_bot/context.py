"""What the outbox and the handlers share: dependencies, entity state rules and
best-effort Telegram calls."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from fhc_api.admin_bot.codec import Kind, channel_token, state_token
from fhc_api.admin_bot.settings import AdminBotConfig
from fhc_api.db import ConnFactory
from fhc_api.publishing.service import ChannelPublisher
from fhc_api.telegram.client import TelegramAPIError, TelegramClient, TelegramError
from fhc_api.web.revalidate import Revalidator

logger = logging.getLogger("fhc_api.admin_bot")

# The status a message kind is about; a message is current only while its entity is in it.
KIND_STATUS: dict[Kind, str] = {
    "review": "in_review",
    "publish": "approved",
    "application": "new",
    "channel_post": "published",
    "channel_update": "published",
}


@dataclass(frozen=True)
class BotContext:
    config: AdminBotConfig
    client: TelegramClient
    # Short pool checkouts, one per unit of work; never held during a Telegram call.
    open_conn: ConnFactory
    revalidator: Revalidator
    # Ask the runner for an outbox scan before the next long poll.
    request_scan: Callable[[], None]
    # Sleep that returns True when the bot is stopping (pacing between sends).
    sleep: Callable[[float], bool]
    # True once shutdown started: loops over Telegram calls stop early.
    stopping: Callable[[], bool]
    # Channel publishing (V1.1a), only when it is configured: enables the channel offers.
    channel: ChannelPublisher | None = None


def current_token(
    kind: Kind, status: str | None, updated_at: datetime | None, channel_marker: str = ""
) -> str | None:
    """The state token a live message of this kind must carry for the entity as it is
    now; None when no message of this kind should be live (wrong status or deleted).

    Channel offers also depend on the event's post (`channel_marker`, empty when there is
    none): "Post to channel" only while there is no post, "Update channel post" only while
    there is one."""
    if status != KIND_STATUS[kind] or updated_at is None:
        return None
    if kind == "channel_post":
        return None if channel_marker else channel_token(updated_at, channel_marker)
    if kind == "channel_update":
        return channel_token(updated_at, channel_marker) if channel_marker else None
    return state_token(updated_at)


def best_effort(what: str, call: Callable[[], object]) -> bool:
    """Run a Telegram call whose failure must not undo or block anything (edits, callback
    answers). Errors are logged without content; Telegram error texts never hold the token."""
    try:
        call()
    except TelegramAPIError as exc:
        if "message is not modified" in exc.description:
            return True
        logger.warning("admin bot: %s failed: %s", what, exc)
        return False
    except TelegramError as exc:
        logger.warning("admin bot: %s failed: %s", what, exc)
        return False
    return True

"""Telegram configuration check (TELEGRAM_RESEARCH §4 step 5, MVP criterion 11).

Calls `getMe`, `getChat` and `getChatMember` (for the bot itself) and reports one status.

Error mapping. The Bot API docs only guarantee `{ok: false, error_code, description}` and say
`error_code` "is subject to change", so this mapping is based on the codes Telegram returns in
practice and is deliberately conservative (anything unexpected becomes `error`):

- `getMe` 401 (Unauthorized) or 404 (Not Found, e.g. a revoked/malformed token path)
  -> `invalid_token`
- 400 whose description contains "chat not found" -> `chat_not_found`
- 403 (Forbidden, e.g. "bot is not a member of the channel chat", "bot was kicked")
  -> `bot_not_admin`
- `getChatMember` 400 "user not found" / "member not found" (bot not in chat) -> `bot_not_admin`
"""

from typing import Literal

from pydantic import BaseModel, Field

from fhc_api.telegram.client import (
    TelegramAPIError,
    TelegramClient,
    TelegramError,
    TelegramUser,
)

TelegramCheckStatus = Literal[
    "not_configured",
    "invalid_token",
    "chat_not_found",
    "bot_not_admin",
    "missing_rights",
    "ok",
    "error",
]

# Least privilege (SECURITY §6): posting and editing are required for V1.1 publishing.
# Deleting is only a fallback correction path, so its absence is reported, not fatal.
REQUIRED_CHANNEL_RIGHTS = ("can_post_messages", "can_edit_messages")
OPTIONAL_CHANNEL_RIGHTS = ("can_delete_messages",)
_ADMIN_STATUSES = frozenset({"creator", "administrator"})


class TelegramCheckResult(BaseModel):
    status: TelegramCheckStatus
    message: str
    bot_username: str | None = None
    chat_title: str | None = None
    chat_type: str | None = None
    missing_rights: list[str] = Field(default_factory=list)
    missing_optional_rights: list[str] = Field(default_factory=list)


def _error_result(
    exc: TelegramError, step: str, bot: TelegramUser | None = None
) -> TelegramCheckResult:
    username = bot.username if bot else None
    if isinstance(exc, TelegramAPIError):
        code, description = exc.error_code, exc.description.lower()
        if code in (401, 404) and step == "getMe":
            return TelegramCheckResult(
                status="invalid_token",
                message="Telegram rejected the bot token. Check TELEGRAM_BOT_TOKEN.",
            )
        if code == 400 and "chat not found" in description:
            return TelegramCheckResult(
                status="chat_not_found",
                message="Telegram cannot find the channel. Check TELEGRAM_CHANNEL_ID and that "
                "the bot has been added to the channel.",
                bot_username=username,
            )
        if code == 403 or (
            step == "getChatMember"
            and code == 400
            and ("user not found" in description or "member not found" in description)
        ):
            return TelegramCheckResult(
                status="bot_not_admin",
                message="The bot is not a member of the channel. Add it as an administrator.",
                bot_username=username,
            )
        if code == 429:
            wait = f" Retry after {exc.retry_after} s." if exc.retry_after else ""
            return TelegramCheckResult(
                status="error", message=f"Telegram rate limit.{wait}", bot_username=username
            )
    return TelegramCheckResult(status="error", message=str(exc), bot_username=username)


def run_telegram_check(
    client: TelegramClient | None, channel_id: int | str | None
) -> TelegramCheckResult:
    if client is None or channel_id is None or str(channel_id).strip() == "":
        return TelegramCheckResult(
            status="not_configured",
            message="Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID in services/api/.env.",
        )

    try:
        bot = client.get_me()
    except TelegramError as exc:
        return _error_result(exc, "getMe")

    try:
        chat = client.get_chat(channel_id)
    except TelegramError as exc:
        return _error_result(exc, "getChat", bot)

    def result(
        status: TelegramCheckStatus,
        message: str,
        missing: list[str] | None = None,
        missing_optional: list[str] | None = None,
    ) -> TelegramCheckResult:
        return TelegramCheckResult(
            status=status,
            message=message,
            bot_username=bot.username,
            chat_title=chat.title,
            chat_type=chat.type,
            missing_rights=missing or [],
            missing_optional_rights=missing_optional or [],
        )

    if chat.type != "channel":
        return result(
            "error", f"TELEGRAM_CHANNEL_ID points to a {chat.type} chat; a channel is expected."
        )

    try:
        member = client.get_chat_member(chat.id, bot.id)
    except TelegramError as exc:
        return _error_result(exc, "getChatMember", bot)

    if member.status not in _ADMIN_STATUSES:
        return result(
            "bot_not_admin",
            f"The bot is {member.status!r} in the channel, not an administrator.",
        )

    def lacking(rights: tuple[str, ...]) -> list[str]:
        if member.status == "creator":
            return []
        return [right for right in rights if getattr(member, right) is not True]

    missing = lacking(REQUIRED_CHANNEL_RIGHTS)
    optional = lacking(OPTIONAL_CHANNEL_RIGHTS)
    if missing:
        return result(
            "missing_rights",
            "The bot is an administrator but lacks: " + ", ".join(missing) + ".",
            missing,
            optional,
        )
    if optional:
        return result(
            "ok",
            "Bot token and required channel rights are OK. Optional right missing: "
            + ", ".join(optional)
            + ".",
            missing_optional=optional,
        )
    return result("ok", "Bot token and channel rights are OK.")

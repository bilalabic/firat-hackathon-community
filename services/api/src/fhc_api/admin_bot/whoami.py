"""Print the numeric ids of users who messaged the admin bot, for TELEGRAM_ADMIN_USER_IDS.

Usage (in services/api, with TELEGRAM_ADMIN_BOT_TOKEN in .env):
    1. send /start to the admin bot from your Telegram account;
    2. uv run python -m fhc_api.admin_bot.whoami

It reads pending updates once without confirming them (no offset), so it changes nothing.
Run it while the admin API is stopped or TELEGRAM_ADMIN_ENABLED=false: a running bot
consumes the updates, and Telegram allows only one getUpdates caller at a time.
"""

import sys

from fhc_api.config import Settings
from fhc_api.telegram.client import TelegramClient, TelegramError


def main() -> int:
    settings = Settings()  # type: ignore[call-arg]
    token = settings.TELEGRAM_ADMIN_BOT_TOKEN
    if token is None or not token.get_secret_value().strip():
        print("TELEGRAM_ADMIN_BOT_TOKEN is not set in services/api/.env.", file=sys.stderr)
        return 2
    error: TelegramError | None = None
    try:
        client = TelegramClient(token.get_secret_value())
        try:
            bot = client.get_me()
            updates = client.get_updates(
                offset=None, timeout_s=0, allowed_updates=["message", "callback_query"]
            )
        finally:
            client.close()
    except TelegramError as exc:  # messages never contain the token
        error = exc
    if error is not None:
        print(f"Telegram error: {error}", file=sys.stderr)
        return 1

    print(f"Bot: @{bot.username or bot.first_name} (id {bot.id})")
    seen: dict[int, str] = {}
    for update in updates:
        sender = update.message.from_ if update.message else None
        chat = update.message.chat.type if update.message else None
        if update.callback_query is not None:
            sender, chat = update.callback_query.from_, "button press"
        if sender is not None and not sender.is_bot:
            seen[sender.id] = f"{sender.first_name} ({chat})"
    if not seen:
        print("No messages found. Send /start to the bot from your account, then run again.")
        return 0
    for user_id, label in seen.items():
        print(f"user id {user_id}: {label}")
    print("Put your id in services/api/.env: TELEGRAM_ADMIN_USER_IDS=<id>[,<id>...]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

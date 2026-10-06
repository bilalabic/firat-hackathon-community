"""Admin bot configuration, parsed from the raw `TELEGRAM_ADMIN_*` settings.

Parsing never raises into the app factory: a bad value disables the bot with a message
that `GET /admin-bot/status` reports. Messages never contain the token.
"""

import math
import re
from dataclasses import dataclass

from pydantic import SecretStr

from fhc_api.config import Settings

DEFAULT_MAX_PRESS_AGE_H = 12.0
DEFAULT_SCAN_INTERVAL_S = 60.0
MAX_PRESS_AGE_RANGE_H = (0.1, 48.0)
SCAN_INTERVAL_RANGE_S = (10.0, 3600.0)
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"", "0", "false", "no", "off"}
_ID_RE = re.compile(r"[1-9][0-9]{0,19}")


class AdminBotConfigError(ValueError):
    """The admin bot is enabled but cannot start with this configuration."""


@dataclass(frozen=True)
class AdminBotConfig:
    token: SecretStr
    # Numeric Telegram user ids. In a private chat the chat id equals the user id, so these
    # are also the chats that receive notifications.
    admin_ids: frozenset[int]
    max_press_age_h: float = DEFAULT_MAX_PRESS_AGE_H
    scan_interval_s: float = DEFAULT_SCAN_INTERVAL_S

    def __repr__(self) -> str:  # no token, no admin ids
        return (
            f"AdminBotConfig(admins={len(self.admin_ids)}, "
            f"max_press_age_h={self.max_press_age_h}, scan_interval_s={self.scan_interval_s})"
        )


def is_enabled(settings: Settings) -> bool:
    """False unless TELEGRAM_ADMIN_ENABLED is a true value. An unrecognized value is
    treated as enabled so that `load_config` reports it instead of silently ignoring it."""
    raw = (settings.TELEGRAM_ADMIN_ENABLED or "").strip().lower()
    return raw not in _FALSE


def parse_admin_ids(raw: str | None) -> frozenset[int]:
    parts = [part for part in re.split(r"[\s,]+", raw or "") if part]
    if not parts:
        raise AdminBotConfigError(
            "TELEGRAM_ADMIN_USER_IDS is empty; add your numeric Telegram user id "
            "(see `uv run python -m fhc_api.admin_bot.whoami`)"
        )
    if not all(_ID_RE.fullmatch(part) for part in parts):
        raise AdminBotConfigError(
            "TELEGRAM_ADMIN_USER_IDS must be numeric Telegram user ids separated by commas "
            "(usernames are not accepted)"
        )
    return frozenset(int(part) for part in parts)


def _number(raw: str | None, name: str, default: float, bounds: tuple[float, float]) -> float:
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        value = math.nan
    low, high = bounds
    if not low <= value <= high:  # also rejects NaN
        raise AdminBotConfigError(f"{name} must be a number between {low:g} and {high:g}")
    return value


def load_config(settings: Settings) -> AdminBotConfig:
    """Call only when `is_enabled(settings)`. Raises AdminBotConfigError."""
    raw_enabled = (settings.TELEGRAM_ADMIN_ENABLED or "").strip().lower()
    if raw_enabled not in _TRUE:
        raise AdminBotConfigError("TELEGRAM_ADMIN_ENABLED must be true or false")
    token = settings.TELEGRAM_ADMIN_BOT_TOKEN
    if token is None or not token.get_secret_value().strip():
        raise AdminBotConfigError("TELEGRAM_ADMIN_BOT_TOKEN is not set")
    channel_token = settings.TELEGRAM_BOT_TOKEN
    if channel_token is not None and (
        channel_token.get_secret_value().strip() == token.get_secret_value().strip()
    ):
        raise AdminBotConfigError(
            "TELEGRAM_ADMIN_BOT_TOKEN must belong to a separate admin bot, "
            "not the channel bot (TELEGRAM_BOT_TOKEN)"
        )
    return AdminBotConfig(
        token=token,
        admin_ids=parse_admin_ids(settings.TELEGRAM_ADMIN_USER_IDS),
        max_press_age_h=_number(
            settings.TELEGRAM_ADMIN_MAX_PRESS_AGE_H,
            "TELEGRAM_ADMIN_MAX_PRESS_AGE_H",
            DEFAULT_MAX_PRESS_AGE_H,
            MAX_PRESS_AGE_RANGE_H,
        ),
        scan_interval_s=_number(
            settings.TELEGRAM_ADMIN_SCAN_INTERVAL_S,
            "TELEGRAM_ADMIN_SCAN_INTERVAL_S",
            DEFAULT_SCAN_INTERVAL_S,
            SCAN_INTERVAL_RANGE_S,
        ),
    )

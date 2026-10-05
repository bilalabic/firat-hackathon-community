"""Calendar dates in an IANA timezone. Event dates are local dates, so "today"
must be computed in the event's timezone, not in UTC or the laptop's zone."""

from datetime import UTC, date, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo, available_timezones


@lru_cache(maxsize=1)
def _known_timezones() -> frozenset[str]:
    return frozenset(available_timezones())


def is_valid_timezone(name: str) -> bool:
    """True for IANA names known to the tz database (not file paths or `localtime`)."""
    return name in _known_timezones()


def today_in(timezone: str, now: datetime | None = None) -> date:
    """The local calendar date in `timezone` at `now` (default: the current instant)."""
    instant = now if now is not None else datetime.now(UTC)
    if instant.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return instant.astimezone(ZoneInfo(timezone)).date()

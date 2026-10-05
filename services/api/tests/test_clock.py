from datetime import UTC, date, datetime

import pytest

from fhc_api.common.clock import is_valid_timezone, today_in


def test_today_depends_on_the_timezone() -> None:
    # 22:30 UTC on 28 Sep is already 29 Sep in Istanbul (UTC+3) but still 28 Sep in LA.
    instant = datetime(2026, 9, 28, 22, 30, tzinfo=UTC)

    assert today_in("Europe/Istanbul", instant) == date(2026, 9, 29)
    assert today_in("America/Los_Angeles", instant) == date(2026, 9, 28)
    assert today_in("UTC", instant) == date(2026, 9, 28)


def test_naive_now_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        today_in("UTC", datetime(2026, 9, 28, 12, 0))  # deliberately naive


@pytest.mark.parametrize("name", ["Europe/Istanbul", "America/Los_Angeles", "UTC"])
def test_valid_timezones(name: str) -> None:
    assert is_valid_timezone(name)


@pytest.mark.parametrize(
    "name", ["", "Mars/Base", "europe/istanbul", "../../etc/passwd", "localtime", "+03:00"]
)
def test_invalid_timezones(name: str) -> None:
    assert not is_valid_timezone(name)

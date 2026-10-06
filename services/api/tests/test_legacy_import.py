import json
from datetime import date
from pathlib import Path

import pytest

from fhc_api.legacy_import import (
    LOCATIONS,
    first_sentence,
    parse_team_size,
    sql_literal,
    to_row,
    to_sql,
)

EVENTS_JSON = Path(__file__).resolve().parents[3] / "supabase" / "legacy" / "events.json"


def load_legacy() -> list[dict[str, object]]:
    data: list[dict[str, object]] = json.loads(EVENTS_JSON.read_text(encoding="utf-8"))
    return data


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1-4 kişi", (1, 4)),
        ("3 kişi", (3, 3)),
        ("2 - 5", (2, 5)),
        ("2\u20135", (2, 5)),
        ("Belirtilmemiş", (None, None)),
        (None, (None, None)),
    ],
)
def test_parse_team_size(value: str | None, expected: tuple[int | None, int | None]) -> None:
    assert parse_team_size(value) == expected


def test_first_sentence() -> None:
    assert first_sentence("Birinci cümle. İkinci cümle.") == "Birinci cümle."
    assert first_sentence(None) is None
    assert first_sentence("x" * 400) == "x" * 299 + "…"


def test_sql_literal_escapes_quotes() -> None:
    assert sql_literal("Türkiye'nin") == "'Türkiye''nin'"
    assert sql_literal(None) == "null"
    assert sql_literal(3) == "3"
    assert sql_literal(True) == "true"


def test_all_legacy_events_map() -> None:
    raw = load_legacy()
    rows = [to_row(item) for item in raw]

    assert len(rows) == 6
    assert {row.slug for row in rows} == set(LOCATIONS)
    assert all(row.official_url.startswith("https://") for row in rows)
    assert all(row.start_date is not None for row in rows)


def test_legacy_mapping_details() -> None:
    rows = {row.slug: row for row in (to_row(item) for item in load_legacy())}

    borsa = rows["borsa-istanbul-fintech-hackathon"]
    assert borsa.format == "in_person"
    assert (borsa.team_min, borsa.team_max) == (3, 3)
    assert borsa.location.city == "İstanbul"
    assert borsa.application_deadline == date(2026, 9, 11)
    assert borsa.start_date == date(2026, 10, 10)

    grid = rows["grid-up-hackathon"]
    assert grid.format == "online"
    assert grid.location.city is None
    assert grid.official_url_normalized == "patika.dev/bootcamp/grid-up-hackathon"

    greece = rows["greece-turkiye-hackathon-2026"]
    assert (greece.team_min, greece.team_max) == (None, None)


def test_unmapped_event_is_rejected() -> None:
    with pytest.raises(ValueError, match="No location mapping"):
        to_row({"id": "unknown", "name": "X", "url": "https://x.dev"})


def test_to_sql_is_idempotent_statement() -> None:
    sql = to_sql([to_row(item) for item in load_legacy()])
    assert sql.count("on conflict") == 2
    assert "'published'" in sql

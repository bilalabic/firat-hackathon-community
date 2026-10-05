import re
from datetime import date
from typing import Any

import pytest

from fhc_api.publishing.hashing import PUBLISHABLE_FIELDS, canonical_json, publishable_hash

EVENT: dict[str, Any] = {
    "title": "Fırat Hackathon",
    "start_date": date(2026, 10, 10),
    "end_date": date(2026, 10, 11),
    "application_deadline": date(2026, 10, 1),
    "format": "in_person",
    "city": "Elazığ",
    "country": "TR",
    "official_url": "https://example.com/hackathon",
    "application_url": None,
    # not publishable:
    "description": "Long text",
    "internal_notes": "private",
    "updated_at": "2026-09-28T10:00:00Z",
}


def test_hash_is_sha256_hex() -> None:
    assert re.fullmatch(r"[0-9a-f]{64}", publishable_hash(EVENT))


def test_hash_is_stable_under_key_order() -> None:
    reordered = dict(reversed(list(EVENT.items())))

    assert publishable_hash(reordered) == publishable_hash(EVENT)


def test_hash_is_deterministic_for_a_known_projection() -> None:
    # Canonical JSON pins the exact bytes that are hashed (sorted keys, no spaces, UTF-8).
    projection = {field: None for field in PUBLISHABLE_FIELDS} | {"title": "Ç", "city": None}

    assert canonical_json(projection).startswith('{"application_deadline":null,')
    assert '"title":"Ç"' in canonical_json(projection)


@pytest.mark.parametrize("field", PUBLISHABLE_FIELDS)
def test_hash_changes_when_a_projected_field_changes(field: str) -> None:
    changed = {**EVENT, field: "changed"}

    assert publishable_hash(changed) != publishable_hash(EVENT)


@pytest.mark.parametrize("field", ["description", "internal_notes", "updated_at", "new_column"])
def test_hash_ignores_non_projected_fields(field: str) -> None:
    changed = {**EVENT, field: "changed"}

    assert publishable_hash(changed) == publishable_hash(EVENT)


def test_missing_field_hashes_like_null() -> None:
    without = {key: value for key, value in EVENT.items() if key != "application_url"}

    assert publishable_hash(without) == publishable_hash(EVENT)

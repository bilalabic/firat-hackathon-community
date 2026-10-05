"""Model-level validation that needs no database."""

from typing import Any

import pytest
from pydantic import ValidationError

from fhc_api.events.models import EventCreate, EventUpdate
from fhc_api.sources.models import SourceUpdate

BASE: dict[str, Any] = {"title": "Valid title", "official_url": "https://example.com"}


@pytest.mark.parametrize(
    "field",
    [
        "organizer",
        "summary",
        "description",
        "format",
        "city",
        "country",
        "venue",
        "start_date",
        "end_date",
        "application_deadline",
        "eligibility",
        "team_min",
        "team_max",
        "prize_pool",
        "currency",
        "is_free",
        "application_url",
        "poster_url",
        "banner_url",
        "organizer_logo_url",
        "internal_notes",
    ],
)
def test_every_optional_event_field_accepts_null(field: str) -> None:
    assert getattr(EventCreate.model_validate({**BASE, field: None}), field) is None
    assert EventUpdate.model_validate({field: None}).changes() == {field: None}


@pytest.mark.parametrize("field", ["organizer", "city", "application_url", "country", "currency"])
def test_blank_strings_become_null(field: str) -> None:
    assert getattr(EventCreate.model_validate({**BASE, field: "   "}), field) is None


def test_codes_are_upper_cased() -> None:
    event = EventCreate.model_validate(
        {**BASE, "country": "tr", "currency": "try", "prize_pool": "10.50"}
    )

    assert (event.country, event.currency) == ("TR", "TRY")


def test_tags_are_normalized_and_deduplicated() -> None:
    event = EventCreate.model_validate(
        {**BASE, "categories": ["AI", " ai ", "fintech"], "technologies": ["Node.js"]}
    )

    assert event.categories == ["ai", "fintech"]
    assert event.technologies == ["node.js"]


@pytest.mark.parametrize("field", EventUpdate.not_null_fields)
def test_not_null_event_fields_reject_null_on_patch(field: str) -> None:
    with pytest.raises(ValidationError, match=f"cannot be null: {field}"):
        EventUpdate.model_validate({field: None})


def test_source_update_rejects_null_for_required_fields_but_not_notes() -> None:
    with pytest.raises(ValidationError, match="cannot be null: tier"):
        SourceUpdate(tier=None)

    assert SourceUpdate(notes=None, base_url=None).changes() == {"notes": None, "base_url": None}

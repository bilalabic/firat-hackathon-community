"""Publishable hash (DATA_MODEL `publications.content_hash`).

"Changed since published" compares the current event's hash with the hash stored when
it was last sent. Only fields that appear in a publication (the Telegram caption and the
event card) are hashed, so editing internal notes or the description does not mark an
event as changed.

The card hash covers only what the `opengraph-image` card shows. It versions the card URL
(`?v=`), so an edit that changes the card makes Telegram fetch the new image, while an edit
that only changes the caption (e.g. the summary) keeps the image as it is.
"""

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

# What `apps/web/src/app/hackathonlar/[slug]/opengraph-image.tsx` renders.
CARD_FIELDS = (
    "title",
    "organizer",
    "start_date",
    "end_date",
    "application_deadline",
    "format",
    "venue",
    "city",
    "country",
)

# The card plus what only the caption shows (`fhc_api.publishing.caption`).
PUBLISHABLE_FIELDS = (
    *CARD_FIELDS,
    "summary",
    "team_min",
    "team_max",
    "official_url",
    "application_url",
)


def _json_value(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    return value


def _projection(event: Mapping[str, Any], fields: Sequence[str]) -> dict[str, Any]:
    return {field: _json_value(event.get(field)) for field in fields}


def publishable_projection(event: Mapping[str, Any]) -> dict[str, Any]:
    return _projection(event, PUBLISHABLE_FIELDS)


def canonical_json(data: Mapping[str, Any]) -> str:
    """Sorted keys, no insignificant whitespace, UTF-8 text kept as is."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(data: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def publishable_hash(event: Mapping[str, Any]) -> str:
    """SHA-256 hex digest of the canonical JSON of the publishable projection."""
    return _sha256(publishable_projection(event))


def card_hash(event: Mapping[str, Any]) -> str:
    """SHA-256 hex digest of the card fields only."""
    return _sha256(_projection(event, CARD_FIELDS))

"""Publishable hash (DATA_MODEL `publications.content_hash`).

"Changed since published" compares the current event's hash with the hash stored when
it was last sent. Only fields that appear in a publication are hashed, so editing
internal notes or the description does not mark an event as changed.
"""

import hashlib
import json
from collections.abc import Mapping
from datetime import date
from typing import Any

PUBLISHABLE_FIELDS = (
    "title",
    "start_date",
    "end_date",
    "application_deadline",
    "format",
    "city",
    "country",
    "official_url",
    "application_url",
)


def _json_value(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    return value


def publishable_projection(event: Mapping[str, Any]) -> dict[str, Any]:
    return {field: _json_value(event.get(field)) for field in PUBLISHABLE_FIELDS}


def canonical_json(data: Mapping[str, Any]) -> str:
    """Sorted keys, no insignificant whitespace, UTF-8 text kept as is."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def publishable_hash(event: Mapping[str, Any]) -> str:
    """SHA-256 hex digest of the canonical JSON of the publishable projection."""
    payload = canonical_json(publishable_projection(event)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

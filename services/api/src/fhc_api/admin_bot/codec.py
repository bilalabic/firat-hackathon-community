"""`callback_data` for the admin bot's inline buttons.

Format: `v1:<action>:<entity type>:<id, 32 hex>:<state token, 8 hex>` (at most 50 bytes;
Bot API limit: 1-64 bytes). The state token is a short hash of the entity state the
buttons were made for, so a press on an outdated message is detected and refused.
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fhc_api.common.audit import EntityType

CALLBACK_DATA_MAX_BYTES = 64

Action = Literal[
    # review message (event in review)
    "approve",
    "request_changes",
    "reject",
    "reject_confirm",
    # publish prompt (approved event)
    "publish",
    "publish_confirm",
    "later",
    # both event messages: back from a confirmation to the original buttons
    "cancel",
    # application message (status `new`)
    "contacted",
    "accepted",
    "declined",
    "spam",
]
Kind = Literal["review", "publish", "application"]

_ACTION_CODES: dict[Action, str] = {
    "approve": "ap",
    "request_changes": "rc",
    "reject": "rj",
    "reject_confirm": "rjc",
    "publish": "pb",
    "publish_confirm": "pbc",
    "later": "lt",
    "cancel": "cx",
    "contacted": "co",
    "accepted": "ac",
    "declined": "de",
    "spam": "sp",
}
_CODE_ACTIONS: dict[str, Action] = {code: action for action, code in _ACTION_CODES.items()}
_ENTITY_CODES: dict[EntityType, str] = {
    "event": "e",
    "community_application": "c",
    "team_application": "t",
}
_CODE_ENTITIES: dict[str, EntityType] = {code: kind for kind, code in _ENTITY_CODES.items()}

# Which buttons belong on which message.
KIND_ACTIONS: dict[Kind, frozenset[Action]] = {
    "review": frozenset({"approve", "request_changes", "reject", "reject_confirm", "cancel"}),
    "publish": frozenset({"publish", "publish_confirm", "later", "cancel"}),
    "application": frozenset({"contacted", "accepted", "declined", "spam"}),
}

_DATA_RE = re.compile(r"v1:([a-z]{2,3}):([a-z]):([0-9a-f]{32}):([0-9a-f]{8})")


@dataclass(frozen=True)
class Callback:
    action: Action
    entity_type: EntityType
    entity_id: UUID
    token: str


def encode(callback: Callback) -> str:
    data = (
        f"v1:{_ACTION_CODES[callback.action]}:{_ENTITY_CODES[callback.entity_type]}:"
        f"{callback.entity_id.hex}:{callback.token}"
    )
    if len(data.encode()) > CALLBACK_DATA_MAX_BYTES or not _DATA_RE.fullmatch(data):
        raise ValueError("invalid callback data")
    return data


def decode(data: str | None) -> Callback | None:
    """None for anything that is not a well-formed button of this bot."""
    match = _DATA_RE.fullmatch(data or "")
    if match is None:
        return None
    code, entity_code, entity_hex, token = match.groups()
    action = _CODE_ACTIONS.get(code)
    entity_type = _CODE_ENTITIES.get(entity_code)
    if action is None or entity_type is None:
        return None
    if (entity_type == "event") == (action in KIND_ACTIONS["application"]):
        return None
    return Callback(action, entity_type, UUID(hex=entity_hex), token)


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:8]


def event_token(updated_at: datetime) -> str:
    """Changes with every write to the event (the `updated_at` trigger)."""
    if updated_at.tzinfo is None:
        raise ValueError("updated_at must be timezone-aware")
    return _short_hash("event:" + updated_at.astimezone(UTC).isoformat())


def application_token(status: str) -> str:
    return _short_hash("application:" + status)

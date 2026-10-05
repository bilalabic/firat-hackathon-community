from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from fhc_api.events.models import EventStatus

SignalKey = Literal[
    "official_url_reachable",
    "registration_url_present",
    "dates_coherent",
    "deadline_missing",
    "deadline_passed",
    "possible_duplicate",
    "supporting_sources",
]
SignalStatus = Literal["pass", "warn", "fail", "info"]
DuplicateMatch = Literal["official_url", "title_and_start_date"]


class Signal(BaseModel):
    key: SignalKey
    status: SignalStatus
    detail: str
    blocks_approval: bool = Field(
        description="True when this failing check also makes `approve`/`publish` return 409"
    )


class DuplicateCandidate(BaseModel):
    id: UUID
    slug: str
    title: str
    status: EventStatus
    matches: list[DuplicateMatch]


class TierCount(BaseModel):
    tier: int | None = Field(description="Source tier 1-4; null for URLs without a source")
    count: int


class ReviewOut(BaseModel):
    event_id: UUID
    signals: list[Signal]
    duplicates: list[DuplicateCandidate]
    sources_by_tier: list[TierCount]

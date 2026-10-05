from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from fhc_api.common.fields import (
    HttpUrlStr,
    OptionalHttpsUrl,
    OptionalHttpUrl,
    OptionalText,
    Tags,
    Text,
    Timezone,
)
from fhc_api.common.models import PartialUpdate
from fhc_api.common.pagination import Page

EventStatus = Literal["draft", "in_review", "approved", "published", "archived", "rejected"]
EventAction = Literal[
    "submit", "approve", "reject", "request_changes", "publish", "unpublish", "archive", "reopen"
]
VerificationStatus = Literal["unverified", "partially_verified", "verified"]
EventFormat = Literal["in_person", "online", "hybrid"]

DEFAULT_TIMEZONE = "Europe/Istanbul"


def _upper_or_none(value: object) -> object:
    if isinstance(value, str):
        return value.strip().upper() or None
    return value


CountryCode = Annotated[  # ISO 3166-1 alpha-2
    Annotated[str, Field(pattern=r"^[A-Z]{2}$")] | None, BeforeValidator(_upper_or_none)
]
CurrencyCode = Annotated[  # ISO 4217
    Annotated[str, Field(pattern=r"^[A-Z]{3}$")] | None, BeforeValidator(_upper_or_none)
]
TeamSize = Annotated[int | None, Field(ge=1, le=20)]
PrizePool = Annotated[Decimal | None, Field(ge=0, max_digits=12, decimal_places=2)]


class EventUpdate(PartialUpdate):
    """Partial update. `null` clears an optional field; the fields in `not_null_fields`
    reject it. The slug is never changed after creation: it is the public URL."""

    not_null_fields = (
        "title",
        "official_url",
        "timezone",
        "categories",
        "technologies",
        "verification_status",
    )

    title: Text | None = Field(default=None, min_length=3, max_length=160)
    organizer: OptionalText = Field(default=None, max_length=160)
    summary: OptionalText = Field(default=None, max_length=300)
    description: OptionalText = Field(default=None, max_length=5000)
    categories: Tags | None = Field(default=None, max_length=10)
    technologies: Tags | None = Field(default=None, max_length=30)
    format: EventFormat | None = None
    city: OptionalText = Field(default=None, max_length=120)
    country: CountryCode = None
    venue: OptionalText = Field(default=None, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    application_deadline: date | None = None
    timezone: Timezone | None = None
    eligibility: OptionalText = Field(default=None, max_length=500)
    team_min: TeamSize = None
    team_max: TeamSize = None
    prize_pool: PrizePool = None
    currency: CurrencyCode = None
    is_free: bool | None = None
    official_url: HttpUrlStr | None = None
    application_url: OptionalHttpUrl = None
    poster_url: OptionalHttpsUrl = None
    banner_url: OptionalHttpsUrl = None
    organizer_logo_url: OptionalHttpsUrl = None
    verification_status: VerificationStatus | None = None
    internal_notes: OptionalText = Field(default=None, max_length=5000)


class EventCreate(EventUpdate):
    title: Text = Field(min_length=3, max_length=160)
    official_url: HttpUrlStr
    categories: Tags = Field(default_factory=list, max_length=10)
    technologies: Tags = Field(default_factory=list, max_length=30)
    timezone: Timezone = DEFAULT_TIMEZONE
    verification_status: VerificationStatus = "unverified"


class EventOut(BaseModel):
    id: UUID
    slug: str
    title: str
    organizer: str | None
    summary: str | None
    description: str | None
    categories: list[str]
    technologies: list[str]
    format: EventFormat | None
    city: str | None
    country: str | None
    venue: str | None
    start_date: date | None
    end_date: date | None
    application_deadline: date | None
    timezone: str
    eligibility: str | None
    team_min: int | None
    team_max: int | None
    prize_pool: Decimal | None
    currency: str | None
    is_free: bool | None
    official_url: str
    official_url_normalized: str
    application_url: str | None
    poster_url: str | None
    banner_url: str | None
    organizer_logo_url: str | None
    status: EventStatus
    verification_status: VerificationStatus
    duplicate_of: UUID | None
    internal_notes: str | None
    created_at: datetime
    updated_at: datetime
    discovered_at: datetime | None
    verified_at: datetime | None
    published_at: datetime | None
    archived_at: datetime | None
    allowed_actions: list[EventAction] = Field(
        description="Transitions the state machine allows from the current status. "
        "Guards (required fields, dates, URL) are checked when the action is sent."
    )


class EventPage(Page[EventOut]):
    pass


class EventTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: EventAction
    reason: OptionalText = Field(
        default=None,
        max_length=1000,
        description="Required for `reject`. When given, it is appended to `internal_notes`.",
    )

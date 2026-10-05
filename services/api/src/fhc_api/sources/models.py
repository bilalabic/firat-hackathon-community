from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from fhc_api.common.fields import HttpUrlStr, OptionalHttpUrl, OptionalText, Text
from fhc_api.common.models import PartialUpdate

SourceKind = Literal[
    "organizer_site", "event_platform", "social", "aggregator", "university", "community", "manual"
]
RetrievalMethod = Literal["manual", "api", "json_endpoint", "rss", "html", "browser"]
SourceRole = Literal["official", "registration", "discovery", "announcement"]
Tier = Literal[1, 2, 3, 4]


class SourceUpdate(PartialUpdate):
    not_null_fields = ("name", "kind", "tier", "retrieval_method", "enabled", "requires_js")

    name: Text | None = Field(default=None, min_length=2, max_length=120)
    kind: SourceKind | None = None
    tier: Tier | None = None
    base_url: OptionalHttpUrl = None
    retrieval_method: RetrievalMethod | None = None
    enabled: bool | None = None
    requires_js: bool | None = None
    notes: OptionalText = Field(default=None, max_length=2000)


class SourceCreate(SourceUpdate):
    name: Text = Field(min_length=2, max_length=120)
    kind: SourceKind
    tier: Tier
    retrieval_method: RetrievalMethod = "manual"
    enabled: bool = True
    requires_js: bool = False


class SourceOut(BaseModel):
    id: UUID
    name: str
    kind: SourceKind
    tier: int
    base_url: str | None
    retrieval_method: RetrievalMethod
    enabled: bool
    requires_js: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime


class EventSourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: HttpUrlStr
    role: SourceRole
    source_id: UUID | None = None


class EventSourceOut(BaseModel):
    id: UUID
    event_id: UUID
    source_id: UUID | None
    source_name: str | None
    source_tier: int | None
    url: str
    url_normalized: str
    role: SourceRole
    first_seen_at: datetime
    last_checked_at: datetime | None
    last_http_status: int | None
    content_hash: str | None

"""API models for URL import (V1.2). The pipeline types are in `importing/models.py`."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from fhc_api.common.fields import HttpUrlStr
from fhc_api.common.pagination import Page
from fhc_api.importing.models import FlagKind

RunKind = Literal["url_import"]
RunStatus = Literal["running", "succeeded", "failed"]
EvidenceSource = Literal["jsonld", "meta", "llm", "manual"]
ImportOutcome = Literal["created", "duplicate"]


class UrlImportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: HttpUrlStr = Field(description="The event page (http or https, public host)")


class RunOut(BaseModel):
    id: UUID
    kind: RunKind
    status: RunStatus = Field(
        description="running (in progress, or interrupted when it stays running), "
        "succeeded or failed"
    )
    url: str | None = Field(description="The requested URL (`input.url`)")
    event_id: UUID | None = Field(description="The created event (or the existing duplicate)")
    error: str | None = Field(description="Operator-facing reason of a failed run")
    stats: dict[str, Any] = Field(
        description="Durations (ms), field and flag counts, extracted_by, llm_error, "
        "final_url, image_url (og:image suggestion, never downloaded)"
    )
    started_at: datetime
    finished_at: datetime | None


class RunPage(Page[RunOut]):
    pass


class UrlImportOut(BaseModel):
    outcome: ImportOutcome = Field(
        description="created: a new draft event; duplicate: an event with the same "
        "normalized official URL exists (nothing was created)"
    )
    event_id: UUID
    run: RunOut | None = Field(description="Null for a duplicate found before fetching")


class FlagOut(BaseModel):
    kind: FlagKind
    detail: str


class FieldEvidenceOut(BaseModel):
    field: str
    value_text: str | None = Field(description="The proposed value; null when it was dropped")
    source: EvidenceSource | None
    extracted_by: str | None
    snippet: str | None = Field(description="Supporting text from the page")
    flags: list[FlagOut]
    matches_current: bool | None = Field(
        description="The event still has the proposed value; null without a value"
    )


class EvidenceOut(BaseModel):
    event_id: UUID
    run: RunOut | None = Field(description="The import that produced the evidence")
    extracted_at: datetime | None
    fields: list[FieldEvidenceOut] = Field(description="Latest import only, in form order")

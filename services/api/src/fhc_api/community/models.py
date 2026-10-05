"""Community and team applications. These rows are personal data: they are returned
only by authenticated endpoints and are never logged."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from fhc_api.common.pagination import Page

ApplicationStatus = Literal["new", "contacted", "accepted", "declined", "spam"]


class ApplicationStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ApplicationStatus


class CommunityApplicationOut(BaseModel):
    id: UUID
    full_name: str
    university: str | None
    field_of_study: str | None
    year_of_study: str | None
    interests: list[str]
    experience_level: str | None
    looking_for: str | None
    preferred_channel: Literal["telegram", "whatsapp"]
    telegram_username: str | None
    phone: str | None
    message: str | None
    consent_version: str
    consented_at: datetime
    status: ApplicationStatus
    created_at: datetime


class TeamApplicationOut(BaseModel):
    id: UUID
    full_name: str
    affiliation: str | None
    areas: list[str]
    skills: str | None
    github_url: str | None
    linkedin_url: str | None
    availability: str | None
    motivation: str | None
    consent_version: str
    consented_at: datetime
    status: ApplicationStatus
    created_at: datetime


class CommunityApplicationPage(Page[CommunityApplicationOut]):
    pass


class TeamApplicationPage(Page[TeamApplicationOut]):
    pass

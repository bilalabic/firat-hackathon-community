"""API models for Telegram channel publishing (V1.1a)."""

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from fhc_api.common.pagination import Page
from fhc_api.events.models import EventStatus

PublicationStatus = Literal["draft", "sent", "edited", "deleted", "failed"]
MessageType = Literal["photo", "text"]
PostState = Literal["not_posted", "sending", "posted", "changed", "not_public"]


class PublicationOut(BaseModel):
    """One Telegram message (`app.publications`). Edits update the row in place
    (`content_version` + 1); the audit list keeps one entry per operation."""

    id: UUID
    event_id: UUID
    platform: Literal["telegram"]
    target: str = Field(description="Channel chat id (numeric once sent)")
    external_id: str | None = Field(description="Telegram message_id")
    content_hash: str
    content_version: int
    body: str = Field(description="Exact caption/text sent (HTML)")
    image_url: str | None = Field(description="Exact card URL sent; null for a text post")
    message_type: MessageType | None
    status: PublicationStatus
    sent_at: datetime | None
    edited_at: datetime | None
    deleted_at: datetime | None
    error: str | None = Field(description="Last error or fallback note (never a token)")
    created_at: datetime


class ChannelPreview(BaseModel):
    event_id: UUID
    slug: str
    title: str
    event_status: EventStatus
    configured: bool = Field(description="Channel bot, channel and WEB_BASE_URL (https) are set")
    config_problem: str | None
    caption_html: str = Field(description="Exactly what is sent (parse_mode HTML)")
    caption_text: str = Field(description="What readers see (tags removed)")
    caption_length: int = Field(description="Visible length in UTF-16 units; limit 1024")
    caption_truncated: bool
    image_url: str | None = Field(description="Event card URL; null without WEB_BASE_URL")
    detail_url: str | None
    content_hash: str
    post_state: PostState = Field(
        description="not_posted; sending (a send is in progress); posted; changed (the "
        "caption or card differs from the live post); not_public (posted, but the event is "
        "no longer published: delete the post if needed)"
    )
    card_changed: bool = Field(description="The live post shows an outdated card")
    current_post: PublicationOut | None = Field(description="The draft or live post")
    can_send: bool
    can_update: bool
    can_delete: bool


class ChannelPostSummary(BaseModel):
    event_id: UUID
    slug: str
    title: str
    event_status: EventStatus
    start_date: date | None
    post_state: PostState
    current_post: PublicationOut | None


class ChannelPostPage(Page[ChannelPostSummary]):
    pass


class ChannelSendIn(BaseModel):
    content_hash: str = Field(
        pattern=r"^[0-9a-f]{64}$",
        description="`content_hash` of the preview being confirmed; a different current hash "
        "(the event changed since the preview) is refused with 409",
    )


class ChannelDeleteIn(BaseModel):
    publication_id: UUID = Field(description="The post shown in the preview")


ActionOutcome = Literal[
    "sent",
    "sent_as_text",
    "edited",
    "edited_caption_only",
    "unchanged",
    "deleted",
    "already_gone",
]


class ChannelActionOut(BaseModel):
    outcome: ActionOutcome = Field(
        description="sent_as_text: the card could not be fetched, a text post with a link "
        "preview was sent; edited_caption_only: the new card could not be fetched, only the "
        "caption changed; already_gone: the message no longer existed in the channel"
    )
    message: str
    publication: PublicationOut


class AuditEntry(BaseModel):
    actor: str
    action: str
    detail: dict[str, Any]
    at: datetime


class ChannelHistory(BaseModel):
    posts: list[PublicationOut] = Field(description="Newest first, including failed attempts")
    actions: list[AuditEntry] = Field(description="Telegram audit entries, newest first")

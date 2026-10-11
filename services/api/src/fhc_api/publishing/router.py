"""`/telegram/channel/...`: preview, send, update, delete, resolve and history of channel
posts. No authentication here; the application adds it globally. Writes take short pool
checkouts (`ConnFactoryDep`), so no connection is held during a Bot API call."""

from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from fhc_api.common.audit import ADMIN_UI
from fhc_api.common.errors import error_responses
from fhc_api.common.pagination import DEFAULT_LIMIT, Limit, Offset
from fhc_api.db import ConnFactoryDep, DbConn
from fhc_api.publishing.models import (
    ChannelActionOut,
    ChannelDeleteIn,
    ChannelHistory,
    ChannelPostPage,
    ChannelPreview,
    ChannelResolveIn,
    ChannelSendIn,
)
from fhc_api.publishing.service import ChannelPublisher

_WRITE_ERRORS = error_responses(404, 409, 422, 502)


def build_channel_router(get_publisher: Callable[[], ChannelPublisher]) -> APIRouter:
    router = APIRouter(prefix="/telegram/channel", tags=["telegram"])
    Publisher = Annotated[ChannelPublisher, Depends(get_publisher)]

    @router.get("/posts", operation_id="list_channel_posts", response_model=ChannelPostPage)
    def list_channel_posts(
        conn: DbConn, publisher: Publisher, limit: Limit = DEFAULT_LIMIT, offset: Offset = 0
    ) -> ChannelPostPage:
        """Published events, and unpublished/archived events that still have a post (first)."""
        return publisher.list_posts(conn, limit=limit, offset=offset)

    @router.get(
        "/events/{event_id}/preview",
        operation_id="preview_channel_post",
        response_model=ChannelPreview,
        responses=error_responses(404),
    )
    def preview_channel_post(conn: DbConn, publisher: Publisher, event_id: UUID) -> ChannelPreview:
        return publisher.preview(conn, event_id)

    @router.get(
        "/events/{event_id}/history",
        operation_id="list_channel_post_history",
        response_model=ChannelHistory,
        responses=error_responses(404),
    )
    def list_channel_post_history(
        conn: DbConn, publisher: Publisher, event_id: UUID
    ) -> ChannelHistory:
        return publisher.history(conn, event_id)

    @router.post(
        "/events/{event_id}/send",
        operation_id="send_channel_post",
        response_model=ChannelActionOut,
        responses=_WRITE_ERRORS,
    )
    def send_channel_post(
        open_conn: ConnFactoryDep, publisher: Publisher, event_id: UUID, body: ChannelSendIn
    ) -> ChannelActionOut:
        """Published events only; refused while a post exists (unless it was deleted).
        502 when Telegram refuses or does not answer (the attempt is recorded as failed)."""
        return publisher.send(open_conn, event_id, actor=ADMIN_UI, expected_hash=body.content_hash)

    @router.post(
        "/events/{event_id}/update",
        operation_id="update_channel_post",
        response_model=ChannelActionOut,
        responses=_WRITE_ERRORS,
    )
    def update_channel_post(
        open_conn: ConnFactoryDep, publisher: Publisher, event_id: UUID, body: ChannelSendIn
    ) -> ChannelActionOut:
        """Edits the caption, and the photo when the card changed (content_version + 1)."""
        return publisher.update(
            open_conn, event_id, actor=ADMIN_UI, expected_hash=body.content_hash
        )

    @router.post(
        "/events/{event_id}/delete",
        operation_id="delete_channel_post",
        response_model=ChannelActionOut,
        responses=_WRITE_ERRORS,
    )
    def delete_channel_post(
        open_conn: ConnFactoryDep, publisher: Publisher, event_id: UUID, body: ChannelDeleteIn
    ) -> ChannelActionOut:
        """Also for events that are no longer public. Telegram may refuse posts older than
        48 hours (TELEGRAM_RESEARCH T-1): 502 with instructions, the post stays live."""
        return publisher.delete(open_conn, event_id, body.publication_id, actor=ADMIN_UI)

    @router.post(
        "/events/{event_id}/posts/{publication_id}/resolve",
        operation_id="resolve_channel_post",
        response_model=ChannelActionOut,
        responses=error_responses(404, 409, 422),
    )
    def resolve_channel_post(
        open_conn: ConnFactoryDep,
        publisher: Publisher,
        event_id: UUID,
        publication_id: UUID,
        body: ChannelResolveIn,
    ) -> ChannelActionOut:
        """For a post in post_state `uncertain` (a send timed out, got an unreadable answer
        or was interrupted): the operator checked the channel and the message is not there
        (or deleted it there by hand). Marks the post failed, so a new send is allowed;
        audited. 409 for any other post. No Bot API call."""
        return publisher.resolve(open_conn, event_id, publication_id, body.outcome, actor=ADMIN_UI)

    return router

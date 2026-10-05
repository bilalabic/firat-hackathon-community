from uuid import UUID

from fastapi import APIRouter, Response, status

from fhc_api.common.errors import error_responses, not_found
from fhc_api.common.normalize import normalize_url
from fhc_api.db import Conn, DbConn
from fhc_api.events import repository as events_repository
from fhc_api.sources import repository
from fhc_api.sources.models import (
    EventSourceCreate,
    EventSourceOut,
    SourceCreate,
    SourceOut,
    SourceUpdate,
)

router = APIRouter(prefix="/sources", tags=["sources"])
event_sources_router = APIRouter(prefix="/events/{event_id}/sources", tags=["event sources"])


@router.get("", operation_id="list_sources", response_model=list[SourceOut])
def list_sources(conn: DbConn) -> list[SourceOut]:
    return [SourceOut.model_validate(row) for row in repository.list_sources(conn)]


@router.post(
    "",
    operation_id="create_source",
    response_model=SourceOut,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(409, 422),
)
def create_source(conn: DbConn, body: SourceCreate) -> SourceOut:
    return SourceOut.model_validate(repository.insert_source(conn, body.model_dump()))


@router.patch(
    "/{source_id}",
    operation_id="update_source",
    response_model=SourceOut,
    responses=error_responses(404, 409, 422),
)
def update_source(conn: DbConn, source_id: UUID, body: SourceUpdate) -> SourceOut:
    changes = body.changes()
    row = (
        repository.update_source(conn, source_id, changes)
        if changes
        else repository.get_source(conn, source_id)
    )
    if row is None:
        raise not_found("source")
    return SourceOut.model_validate(row)


def _require_event(conn: Conn, event_id: UUID) -> None:
    if events_repository.get(conn, event_id) is None:
        raise not_found("event")


@event_sources_router.get(
    "",
    operation_id="list_event_sources",
    response_model=list[EventSourceOut],
    responses=error_responses(404),
)
def list_event_sources(conn: DbConn, event_id: UUID) -> list[EventSourceOut]:
    _require_event(conn, event_id)
    return [
        EventSourceOut.model_validate(row) for row in repository.list_event_sources(conn, event_id)
    ]


@event_sources_router.post(
    "",
    operation_id="add_event_source",
    response_model=EventSourceOut,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(404, 409, 422),
)
def add_event_source(conn: DbConn, event_id: UUID, body: EventSourceCreate) -> EventSourceOut:
    with conn.transaction():
        _require_event(conn, event_id)
        values = {
            **body.model_dump(),
            "event_id": event_id,
            "url_normalized": normalize_url(body.url),
        }
        event_source_id = repository.insert_event_source(conn, values)
        row = repository.get_event_source(conn, event_source_id)
    return EventSourceOut.model_validate(row)


@event_sources_router.delete(
    "/{event_source_id}",
    operation_id="remove_event_source",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=error_responses(404),
)
def remove_event_source(conn: DbConn, event_id: UUID, event_source_id: UUID) -> None:
    if not repository.delete_event_source(conn, event_id, event_source_id):
        raise not_found("event source")

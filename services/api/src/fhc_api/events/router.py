from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Query, status

from fhc_api.common.audit import ADMIN_UI
from fhc_api.common.errors import error_responses, not_found
from fhc_api.common.pagination import DEFAULT_LIMIT, Limit, Offset
from fhc_api.db import DbConn
from fhc_api.events import repository, service
from fhc_api.events.models import (
    EventCreate,
    EventOut,
    EventPage,
    EventStatus,
    EventTransition,
    EventUpdate,
)
from fhc_api.web.revalidate import Revalidator, RevalidatorDep, event_tags

router = APIRouter(prefix="/events", tags=["events"])


def _schedule_revalidation(
    result: service.WriteResult, tasks: BackgroundTasks, revalidator: Revalidator
) -> None:
    # Runs after the response is sent; the write has already committed.
    if result.affects_public_site:
        tasks.add_task(revalidator.revalidate, event_tags(result.row["slug"]))


@router.get("", operation_id="list_events", response_model=EventPage)
def list_events(
    conn: DbConn,
    status_filter: Annotated[
        list[EventStatus] | None, Query(alias="status", description="Repeat to match several")
    ] = None,
    upcoming: Annotated[
        bool, Query(description="Only published events whose last day is today or later")
    ] = False,
    closing_within_days: Annotated[
        int | None,
        Query(ge=0, le=60, description="Only published events with a deadline in N days"),
    ] = None,
    limit: Limit = DEFAULT_LIMIT,
    offset: Offset = 0,
) -> EventPage:
    rows, total = repository.list_page(
        conn,
        statuses=status_filter or [],
        upcoming=upcoming,
        closing_within_days=closing_within_days,
        limit=limit,
        offset=offset,
    )
    return EventPage(
        items=[service.to_out(row) for row in rows], total=total, limit=limit, offset=offset
    )


@router.post(
    "",
    operation_id="create_event",
    response_model=EventOut,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(409, 422),
)
def create_event(conn: DbConn, body: EventCreate) -> EventOut:
    return service.to_out(service.create_event(conn, body))


@router.get(
    "/{event_id}", operation_id="get_event", response_model=EventOut, responses=error_responses(404)
)
def get_event(conn: DbConn, event_id: UUID) -> EventOut:
    row = repository.get(conn, event_id)
    if row is None:
        raise not_found("event")
    return service.to_out(row)


@router.patch(
    "/{event_id}",
    operation_id="update_event",
    response_model=EventOut,
    responses=error_responses(404, 409, 422),
)
def update_event(
    conn: DbConn,
    event_id: UUID,
    body: EventUpdate,
    tasks: BackgroundTasks,
    revalidator: RevalidatorDep,
) -> EventOut:
    result = service.update_event(conn, event_id, body)
    _schedule_revalidation(result, tasks, revalidator)
    return service.to_out(result.row)


@router.post(
    "/{event_id}/transitions",
    operation_id="transition_event",
    response_model=EventOut,
    responses=error_responses(404, 409, 422),
)
def transition_event(
    conn: DbConn,
    event_id: UUID,
    body: EventTransition,
    tasks: BackgroundTasks,
    revalidator: RevalidatorDep,
) -> EventOut:
    result = service.transition_event(conn, event_id, body, actor=ADMIN_UI)
    _schedule_revalidation(result, tasks, revalidator)
    return service.to_out(result.row)

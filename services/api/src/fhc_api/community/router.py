"""Read + status update for community (Join Community) and team (Contribute)
applications. Personal data: no logging of request or response contents here."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from fhc_api.common.audit import ADMIN_UI
from fhc_api.common.errors import error_responses
from fhc_api.common.pagination import DEFAULT_LIMIT, Limit, Offset
from fhc_api.community import repository, service
from fhc_api.community.models import (
    ApplicationStatus,
    ApplicationStatusUpdate,
    CommunityApplicationOut,
    CommunityApplicationPage,
    TeamApplicationOut,
    TeamApplicationPage,
)
from fhc_api.db import DbConn

router = APIRouter(tags=["applications"])

StatusFilter = Annotated[
    list[ApplicationStatus] | None, Query(alias="status", description="Repeat to match several")
]


@router.get(
    "/community-applications",
    operation_id="list_community_applications",
    response_model=CommunityApplicationPage,
)
def list_community_applications(
    conn: DbConn,
    status_filter: StatusFilter = None,
    limit: Limit = DEFAULT_LIMIT,
    offset: Offset = 0,
) -> CommunityApplicationPage:
    rows, total = repository.list_page(
        conn, "community_applications", statuses=status_filter or [], limit=limit, offset=offset
    )
    items = [CommunityApplicationOut.model_validate(row) for row in rows]
    return CommunityApplicationPage(items=items, total=total, limit=limit, offset=offset)


@router.patch(
    "/community-applications/{application_id}",
    operation_id="update_community_application",
    response_model=CommunityApplicationOut,
    responses=error_responses(404),
)
def update_community_application(
    conn: DbConn, application_id: UUID, body: ApplicationStatusUpdate
) -> CommunityApplicationOut:
    row = service.set_status(
        conn, "community_applications", application_id, body.status, actor=ADMIN_UI
    )
    return CommunityApplicationOut.model_validate(row)


@router.get(
    "/team-applications",
    operation_id="list_team_applications",
    response_model=TeamApplicationPage,
)
def list_team_applications(
    conn: DbConn,
    status_filter: StatusFilter = None,
    limit: Limit = DEFAULT_LIMIT,
    offset: Offset = 0,
) -> TeamApplicationPage:
    rows, total = repository.list_page(
        conn, "team_applications", statuses=status_filter or [], limit=limit, offset=offset
    )
    items = [TeamApplicationOut.model_validate(row) for row in rows]
    return TeamApplicationPage(items=items, total=total, limit=limit, offset=offset)


@router.patch(
    "/team-applications/{application_id}",
    operation_id="update_team_application",
    response_model=TeamApplicationOut,
    responses=error_responses(404),
)
def update_team_application(
    conn: DbConn, application_id: UUID, body: ApplicationStatusUpdate
) -> TeamApplicationOut:
    row = service.set_status(conn, "team_applications", application_id, body.status, actor=ADMIN_UI)
    return TeamApplicationOut.model_validate(row)

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from fhc_api.common.errors import error_responses, not_found
from fhc_api.db import ConnFactoryDep
from fhc_api.events import repository as events_repository
from fhc_api.events.service import official_url_problem
from fhc_api.review.models import ReviewOut
from fhc_api.review.signals import UrlChecker, compute_signals, count_by_tier, find_duplicates
from fhc_api.sources import repository as sources_repository

router = APIRouter(prefix="/events", tags=["review"])


def get_url_checker(request: Request) -> UrlChecker:
    checker: UrlChecker = request.app.state.url_checker
    return checker


@router.get(
    "/{event_id}/review",
    operation_id="get_event_review",
    response_model=ReviewOut,
    responses=error_responses(404),
)
def get_event_review(
    open_conn: ConnFactoryDep,
    event_id: UUID,
    url_checker: Annotated[UrlChecker, Depends(get_url_checker)],
    check_url: Annotated[
        bool, Query(description="Fetch the official URL (network, up to ~10 s per hop)")
    ] = True,
) -> ReviewOut:
    # All reads happen first; the connection goes back to the pool before the fetch.
    with open_conn() as conn:
        event = events_repository.get(conn, event_id)
        if event is None:
            raise not_found("event")
        candidates = events_repository.find_duplicate_candidates(
            conn, event_id, event["official_url_normalized"], event["start_date"]
        )
        event_sources = sources_repository.list_event_sources(conn, event_id)
    duplicates = find_duplicates(event, candidates)
    sources_by_tier = count_by_tier(event_sources)
    # A statically invalid URL already fails (and blocks approval); never fetch it.
    fetch = check_url and official_url_problem(event["official_url"]) is None
    url_check = url_checker(event["official_url"]) if fetch else None
    return ReviewOut(
        event_id=event_id,
        signals=compute_signals(
            event, url_check=url_check, duplicates=duplicates, sources_by_tier=sources_by_tier
        ),
        duplicates=duplicates,
        sources_by_tier=sources_by_tier,
    )

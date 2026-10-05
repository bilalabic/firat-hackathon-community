from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from fhc_api.common.errors import error_responses, not_found
from fhc_api.db import DbConn
from fhc_api.events import repository as events_repository
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
    conn: DbConn,
    event_id: UUID,
    url_checker: Annotated[UrlChecker, Depends(get_url_checker)],
    check_url: Annotated[
        bool, Query(description="Fetch the official URL (network, up to ~10 s per hop)")
    ] = True,
) -> ReviewOut:
    event = events_repository.get(conn, event_id)
    if event is None:
        raise not_found("event")
    candidates = events_repository.find_duplicate_candidates(
        conn, event_id, event["official_url_normalized"], event["start_date"]
    )
    duplicates = find_duplicates(event, candidates)
    sources_by_tier = count_by_tier(sources_repository.list_event_sources(conn, event_id))
    # Autocommit connection: the fetch runs outside any transaction. It still holds a
    # pooled connection meanwhile, which is fine for a single local admin user.
    url_check = url_checker(event["official_url"]) if check_url else None
    return ReviewOut(
        event_id=event_id,
        signals=compute_signals(
            event, url_check=url_check, duplicates=duplicates, sources_by_tier=sources_by_tier
        ),
        duplicates=duplicates,
        sources_by_tier=sources_by_tier,
    )

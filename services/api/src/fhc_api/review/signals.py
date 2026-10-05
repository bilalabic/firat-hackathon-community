"""Deterministic review signals (LOCAL_ADMIN "Review screen"). No scores: every
signal is a rule with a pass/warn/fail/info outcome and a human-readable detail."""

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from fhc_api.common.clock import today_in
from fhc_api.common.http import FetchError, SafeFetcher
from fhc_api.common.normalize import fold_title
from fhc_api.events.service import date_problems, official_url_problem
from fhc_api.review.models import (
    DuplicateCandidate,
    DuplicateMatch,
    Signal,
    SignalKey,
    TierCount,
)


@dataclass(frozen=True)
class UrlCheck:
    reachable: bool
    detail: str


type UrlChecker = Callable[[str], UrlCheck]


def check_url_reachable(url: str, fetcher: SafeFetcher | None = None) -> UrlCheck:
    """GET through the safe fetcher (headers only); 2xx/3xx counts as reachable."""
    try:
        result = (fetcher or SafeFetcher()).fetch(url, read_body=False)
    except FetchError as exc:
        return UrlCheck(reachable=False, detail=str(exc))
    detail = f"HTTP {result.status_code}"
    if result.redirects:
        detail += f" after {result.redirects} redirect(s) to {result.url}"
    return UrlCheck(reachable=200 <= result.status_code < 400, detail=detail)


def find_duplicates(
    event: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]]
) -> list[DuplicateCandidate]:
    """Same normalized official URL, or same folded title and the same start date."""
    title_key = fold_title(event["title"])
    duplicates = []
    for other in candidates:
        matches: list[DuplicateMatch] = []
        if other["official_url_normalized"] == event["official_url_normalized"]:
            matches.append("official_url")
        if (
            event["start_date"] is not None
            and other["start_date"] == event["start_date"]
            and fold_title(other["title"]) == title_key
        ):
            matches.append("title_and_start_date")
        if matches:
            duplicates.append(
                DuplicateCandidate(
                    id=other["id"],
                    slug=other["slug"],
                    title=other["title"],
                    status=other["status"],
                    matches=matches,
                )
            )
    return duplicates


def count_by_tier(event_sources: Sequence[Mapping[str, Any]]) -> list[TierCount]:
    counts = Counter(row["source_tier"] for row in event_sources)
    ordered = sorted(counts, key=lambda tier: (tier is None, tier or 0))
    return [TierCount(tier=tier, count=counts[tier]) for tier in ordered]


def compute_signals(
    event: Mapping[str, Any],
    *,
    url_check: UrlCheck | None,
    duplicates: Sequence[DuplicateCandidate],
    sources_by_tier: Sequence[TierCount],
    today: date | None = None,
) -> list[Signal]:
    """Pure function of its inputs. `url_check=None` means the network check was skipped;
    `today` defaults to the current date in the event's timezone."""
    today = today or today_in(event["timezone"])
    return [
        _official_url_signal(event, url_check),
        _registration_signal(event),
        _dates_signal(event),
        _deadline_missing_signal(event),
        _deadline_passed_signal(event, today),
        _duplicate_signal(duplicates),
        _sources_signal(sources_by_tier),
    ]


def _official_url_signal(event: Mapping[str, Any], url_check: UrlCheck | None) -> Signal:
    key: SignalKey = "official_url_reachable"
    if problem := official_url_problem(event["official_url"]):
        return Signal(key=key, status="fail", detail=problem, blocks_approval=True)
    if url_check is None:
        return Signal(key=key, status="info", detail="not checked", blocks_approval=False)
    return Signal(
        key=key,
        status="pass" if url_check.reachable else "fail",
        detail=url_check.detail,
        blocks_approval=False,
    )


def _registration_signal(event: Mapping[str, Any]) -> Signal:
    present = event["application_url"] is not None
    return Signal(
        key="registration_url_present",
        status="pass" if present else "warn",
        detail="application_url is set" if present else "application_url is missing",
        blocks_approval=False,
    )


def _dates_signal(event: Mapping[str, Any]) -> Signal:
    problems = date_problems(event)
    return Signal(
        key="dates_coherent",
        status="fail" if problems else "pass",
        detail="; ".join(problems) if problems else "dates are coherent",
        blocks_approval=bool(problems),
    )


def _deadline_missing_signal(event: Mapping[str, Any]) -> Signal:
    missing = event["application_deadline"] is None
    return Signal(
        key="deadline_missing",
        status="warn" if missing else "pass",
        detail="application_deadline is missing" if missing else "application_deadline is set",
        blocks_approval=False,
    )


def _deadline_passed_signal(event: Mapping[str, Any], today: date) -> Signal:
    deadline: date | None = event["application_deadline"]
    key: SignalKey = "deadline_passed"
    if deadline is None:
        return Signal(key=key, status="info", detail="no deadline", blocks_approval=False)
    passed = deadline < today
    detail = (
        f"deadline {deadline.isoformat()} is before today ({today.isoformat()}, "
        f"{event['timezone']})"
        if passed
        else f"deadline {deadline.isoformat()} has not passed ({event['timezone']})"
    )
    return Signal(
        key=key, status="warn" if passed else "pass", detail=detail, blocks_approval=False
    )


def _duplicate_signal(duplicates: Sequence[DuplicateCandidate]) -> Signal:
    detail = (
        "possible duplicate of " + ", ".join(candidate.slug for candidate in duplicates)
        if duplicates
        else "no event with the same official URL or the same title and start date"
    )
    return Signal(
        key="possible_duplicate",
        status="warn" if duplicates else "pass",
        detail=detail,
        blocks_approval=False,
    )


def _sources_signal(sources_by_tier: Sequence[TierCount]) -> Signal:
    if not sources_by_tier:
        return Signal(
            key="supporting_sources",
            status="warn",
            detail="no supporting sources",
            blocks_approval=False,
        )
    parts = [
        f"{'no source' if item.tier is None else f'tier {item.tier}'}: {item.count}"
        for item in sources_by_tier
    ]
    return Signal(
        key="supporting_sources", status="info", detail=", ".join(parts), blocks_approval=False
    )

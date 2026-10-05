"""Review signals: pure rules (no database) and the endpoint (local database)."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from typing import Any
from uuid import uuid4

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fhc_api.common.http import SafeFetcher
from fhc_api.db import Conn, get_conn_factory
from fhc_api.review.models import Signal
from fhc_api.review.signals import (
    UrlCheck,
    check_url_reachable,
    compute_signals,
    count_by_tier,
    find_duplicates,
)
from tests.conftest import MARK, FakeUrlChecker
from tests.factories import create_event, days_from_today

TODAY = date(2026, 9, 28)


def event(**overrides: Any) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "slug": "e",
        "title": "Fırat Hackathon",
        "status": "in_review",
        "official_url": "https://example.com/e",
        "official_url_normalized": "example.com/e",
        "application_url": "https://example.com/apply",
        "start_date": date(2026, 10, 10),
        "end_date": date(2026, 10, 11),
        "application_deadline": date(2026, 10, 1),
        "timezone": "Europe/Istanbul",
        **overrides,
    }


def signals_of(data: dict[str, Any], url_check: UrlCheck | None = None) -> dict[str, Signal]:
    result = compute_signals(
        data,
        url_check=url_check or UrlCheck(reachable=True, detail="HTTP 200"),
        duplicates=[],
        sources_by_tier=count_by_tier([{"source_tier": 1}]),
        today=TODAY,
    )
    return {signal.key: signal for signal in result}


def test_all_signals_pass_for_a_complete_event() -> None:
    signals = signals_of(event())

    assert list(signals) == [
        "official_url_reachable",
        "registration_url_present",
        "dates_coherent",
        "deadline_missing",
        "deadline_passed",
        "possible_duplicate",
        "supporting_sources",
    ]
    assert {key: s.status for key, s in signals.items()} == {
        "official_url_reachable": "pass",
        "registration_url_present": "pass",
        "dates_coherent": "pass",
        "deadline_missing": "pass",
        "deadline_passed": "pass",
        "possible_duplicate": "pass",
        "supporting_sources": "info",
    }
    assert not any(signal.blocks_approval for signal in signals.values())


def test_unreachable_url_fails_without_blocking_approval() -> None:
    signal = signals_of(event(), UrlCheck(reachable=False, detail="HTTP 404"))[
        "official_url_reachable"
    ]

    assert (signal.status, signal.detail, signal.blocks_approval) == ("fail", "HTTP 404", False)


def test_invalid_official_url_blocks_approval() -> None:
    signal = signals_of(event(official_url="http://127.0.0.1/x"))["official_url_reachable"]

    assert signal.status == "fail"
    assert signal.blocks_approval


def test_skipped_url_check_is_info() -> None:
    result = compute_signals(
        event(), url_check=None, duplicates=[], sources_by_tier=[], today=TODAY
    )

    assert result[0].status == "info"
    assert result[0].detail == "not checked"


def test_missing_registration_url_and_deadline_warn() -> None:
    signals = signals_of(event(application_url=None, application_deadline=None))

    assert signals["registration_url_present"].status == "warn"
    assert signals["deadline_missing"].status == "warn"
    assert signals["deadline_passed"].status == "info"


@pytest.mark.parametrize(
    ("overrides", "detail"),
    [
        ({"application_deadline": date(2026, 10, 12)}, "application_deadline is after end_date"),
        (
            {"end_date": None, "application_deadline": date(2026, 10, 11)},
            "application_deadline is after start_date",
        ),
    ],
)
def test_incoherent_dates_fail_and_block(overrides: dict[str, Any], detail: str) -> None:
    signal = signals_of(event(**overrides))["dates_coherent"]

    assert (signal.status, signal.detail, signal.blocks_approval) == ("fail", detail, True)


def test_deadline_passed_uses_the_given_day() -> None:
    assert signals_of(event(application_deadline=TODAY))["deadline_passed"].status == "pass"
    passed = signals_of(event(application_deadline=date(2026, 9, 27)))["deadline_passed"]
    assert passed.status == "warn"
    assert "2026-09-27 is before today (2026-09-28, Europe/Istanbul)" in passed.detail


def test_find_duplicates() -> None:
    subject = event()
    same_url = event(slug="same-url", title="Other", official_url_normalized="example.com/e")
    same_title_day = event(
        slug="same-title", title="  FIRAT hackathon! ", official_url_normalized="other.example"
    )
    same_title_other_day = event(
        slug="other-day",
        title="Fırat Hackathon",
        official_url_normalized="x.example",
        start_date=date(2027, 1, 1),
    )

    duplicates = find_duplicates(subject, [same_url, same_title_day, same_title_other_day])

    assert [(d.slug, d.matches) for d in duplicates] == [
        ("same-url", ["official_url"]),
        ("same-title", ["title_and_start_date"]),
    ]


def test_count_by_tier_orders_unknown_last() -> None:
    rows: list[dict[str, int | None]] = [
        {"source_tier": 2},
        {"source_tier": None},
        {"source_tier": 1},
        {"source_tier": 2},
    ]

    assert [(t.tier, t.count) for t in count_by_tier(rows)] == [(1, 1), (2, 2), (None, 1)]
    assert count_by_tier([]) == []


def test_check_url_reachable_uses_the_safe_fetcher() -> None:
    def safe(status: int) -> SafeFetcher:
        return SafeFetcher(
            resolver=lambda host, port: ["93.184.215.14"],
            transport=httpx2.MockTransport(lambda request: httpx2.Response(status)),
        )

    assert check_url_reachable("https://example.com/", safe(200)) == UrlCheck(True, "HTTP 200")
    assert check_url_reachable("https://example.com/", safe(302)) == UrlCheck(True, "HTTP 302")
    assert check_url_reachable("https://example.com/", safe(503)) == UrlCheck(False, "HTTP 503")
    assert check_url_reachable("https://example.com:8443/", safe(200)) == UrlCheck(
        False, "only ports 80 and 443 are allowed"
    )
    assert check_url_reachable("http://127.0.0.1/", safe(200)) == UrlCheck(
        False, "host resolves to a non-public address"
    )


# --- endpoint -----------------------------------------------------------------------


def test_review_endpoint(client: TestClient, url_checker: FakeUrlChecker) -> None:
    subject = create_event(
        client,
        # Same page as a seeded legacy event (different spelling) -> possible duplicate.
        official_url="https://patika.dev/bootcamp/grid-up-hackathon/",
        application_deadline=days_from_today(-1),
        application_url=None,
    )
    client.post(
        f"/events/{subject['id']}/sources",
        json={"url": "https://pytest-m3.example.com/news", "role": "announcement"},
    )

    response = client.get(f"/events/{subject['id']}/review")

    assert response.status_code == 200
    review = response.json()
    signals = {signal["key"]: signal for signal in review["signals"]}
    assert url_checker.urls == ["https://patika.dev/bootcamp/grid-up-hackathon/"]
    assert signals["official_url_reachable"]["status"] == "pass"
    assert signals["registration_url_present"]["status"] == "warn"
    assert signals["deadline_passed"]["status"] == "warn"
    assert signals["possible_duplicate"]["status"] == "warn"
    assert [d["slug"] for d in review["duplicates"]] == ["grid-up-hackathon"]
    assert review["duplicates"][0]["matches"] == ["official_url"]
    assert review["sources_by_tier"] == [{"tier": None, "count": 1}]
    assert "confidence" not in response.text


def test_review_endpoint_title_duplicate_and_skip_url_check(
    client: TestClient, url_checker: FakeUrlChecker
) -> None:
    first = create_event(client, title=f"{MARK} Twin")
    second = create_event(
        client, title=f"{MARK.upper()} twin!", official_url="https://other.pytest-m3.example.com/"
    )

    review = client.get(f"/events/{second['id']}/review", params={"check_url": False}).json()

    assert url_checker.urls == []
    assert review["signals"][0]["detail"] == "not checked"
    assert [(d["id"], d["matches"]) for d in review["duplicates"]] == [
        (first["id"], ["title_and_start_date"])
    ]


def test_review_unknown_event_is_404(client: TestClient) -> None:
    assert client.get("/events/00000000-0000-0000-0000-000000000000/review").status_code == 404


def test_review_releases_the_connection_before_the_url_fetch(
    app: FastAPI, client: TestClient, db: Conn
) -> None:
    subject = create_event(client)
    steps: list[str] = []

    @contextmanager
    def tracked_conn() -> Iterator[Conn]:
        steps.append("acquire")
        with db.transaction():
            yield db
        steps.append("release")

    def checker(url: str) -> UrlCheck:
        steps.append("fetch")
        return UrlCheck(reachable=True, detail="HTTP 200")

    app.dependency_overrides[get_conn_factory] = lambda: tracked_conn
    app.state.url_checker = checker

    response = client.get(f"/events/{subject['id']}/review")

    assert response.status_code == 200
    assert steps == ["acquire", "release", "fetch"]


def test_review_skips_the_fetch_for_a_statically_invalid_url(
    client: TestClient, url_checker: FakeUrlChecker
) -> None:
    subject = create_event(client, official_url="http://127.0.0.1/internal")

    review = client.get(f"/events/{subject['id']}/review").json()

    assert url_checker.urls == []
    signal = review["signals"][0]
    assert signal["key"] == "official_url_reachable"
    assert (signal["status"], signal["blocks_approval"]) == ("fail", True)
    assert signal["detail"] == "official_url must point to a public host"

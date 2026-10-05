"""Events CRUD and the state machine (MVP criterion 9), against the local database."""

from typing import Any, get_args

import pytest
from fastapi.testclient import TestClient

from fhc_api.common.sql import insert_row
from fhc_api.db import Conn
from fhc_api.events import service
from fhc_api.events.models import EventAction, EventStatus
from fhc_api.events.service import TRANSITIONS
from tests.conftest import MARK, RecordingRevalidator
from tests.factories import create_event, days_from_today, event_payload, force_status

ALL_STATUSES: tuple[EventStatus, ...] = get_args(EventStatus)
ALL_ACTIONS: tuple[EventAction, ...] = get_args(EventAction)


def transition(client: TestClient, event_id: str, action: str, **body: Any) -> Any:
    return client.post(f"/events/{event_id}/transitions", json={"action": action, **body})


# --- create / read / list -----------------------------------------------------------


def test_create_returns_a_draft_with_generated_fields(client: TestClient) -> None:
    event = create_event(
        client,
        title=f"  {MARK} Fırat Şehir Hackathonu  ",
        official_url="https://WWW.Pytest-M3.example.com/Event/?utm_source=x&b=2",
    )

    assert event["status"] == "draft"
    assert event["title"] == f"{MARK} Fırat Şehir Hackathonu"
    assert event["slug"] == "pytest-m3-firat-sehir-hackathonu"
    assert event["official_url_normalized"] == "pytest-m3.example.com/Event?b=2"
    assert event["timezone"] == "Europe/Istanbul"
    assert event["verification_status"] == "unverified"
    assert event["allowed_actions"] == ["submit"]
    assert event["published_at"] is None

    fetched = client.get(f"/events/{event['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == event


def test_slug_collisions_get_numeric_suffixes(client: TestClient) -> None:
    slugs = [create_event(client, title=f"{MARK} Same Title")["slug"] for _ in range(3)]

    assert slugs == ["pytest-m3-same-title", "pytest-m3-same-title-2", "pytest-m3-same-title-3"]


def racing_slug_check(monkeypatch: pytest.MonkeyPatch, db: Conn, races: int) -> list[str]:
    """Make the first `races` slug choices lose a race: right after `_unique_slug` picks a
    slug, a "concurrent" create inserts an event with that slug. Returns the stolen slugs."""
    real_unique_slug = service._unique_slug
    stolen: list[str] = []

    def unique_slug_then_race(conn: Conn, title: str) -> str:
        slug = real_unique_slug(conn, title)
        if len(stolen) < races:
            insert_row(
                db,
                "events",
                {
                    "slug": slug,
                    "title": f"{MARK} Concurrent",
                    "official_url": "https://pytest-m3.example.com/concurrent",
                    "official_url_normalized": "pytest-m3.example.com/concurrent",
                },
            )
            stolen.append(slug)
        return slug

    monkeypatch.setattr(service, "_unique_slug", unique_slug_then_race)
    return stolen


def test_slug_race_is_retried_with_the_next_slug(
    client: TestClient, db: Conn, monkeypatch: pytest.MonkeyPatch
) -> None:
    stolen = racing_slug_check(monkeypatch, db, races=2)

    event = create_event(client, title=f"{MARK} Race")

    assert stolen == ["pytest-m3-race", "pytest-m3-race-2"]
    assert event["slug"] == "pytest-m3-race-3"


def test_slug_race_gives_up_after_three_attempts(
    client: TestClient, db: Conn, monkeypatch: pytest.MonkeyPatch
) -> None:
    stolen = racing_slug_check(monkeypatch, db, races=3)

    response = client.post("/events", json=event_payload(title=f"{MARK} Race"))

    assert len(stolen) == service.SLUG_ATTEMPTS == 3
    assert response.status_code == 409
    assert response.json() == {"detail": "conflicts with an existing row (events_slug_key)"}


def test_slug_collides_with_seeded_legacy_event(client: TestClient) -> None:
    # "grid-up-hackathon" is a seeded legacy slug.
    assert create_event(client, title="Grid Up Hackathon")["slug"] == "grid-up-hackathon-2"


def test_long_title_slug_suffix_stays_within_80_characters(client: TestClient) -> None:
    title = f"{MARK} " + "Çok Uzun Başlık " * 12
    first, second = (create_event(client, title=title[:160])["slug"] for _ in range(2))

    assert len(first) <= 80
    assert len(second) <= 80
    assert second.endswith("-2")
    assert second != first


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"title": "ab"}, "at least 3"),
        ({"official_url": "javascript:alert(1)"}, "scheme"),
        ({"official_url": None}, "string"),
        ({"poster_url": "http://insecure.example/p.png"}, "https"),
        ({"timezone": "Mars/Olympus"}, "IANA"),
        ({"country": "Turkey"}, "pattern"),
        ({"team_min": 0}, "greater than or equal"),
        ({"format": "metaverse"}, "in_person"),
        ({"categories": ["Not A Tag!"]}, "invalid tag"),
        ({"unknown_field": 1}, "Extra inputs"),
    ],
)
def test_create_validation_errors(
    client: TestClient, overrides: dict[str, Any], fragment: str
) -> None:
    response = client.post("/events", json=event_payload(**overrides))

    assert response.status_code == 422
    assert fragment in response.text


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"start_date": "2026-10-10", "end_date": "2026-10-09"},
            "end_date is before start_date",
        ),
        ({"team_min": 5, "team_max": 2}, "team_min is greater than team_max"),
        ({"prize_pool": "1000", "currency": None}, "currency is required when prize_pool is set"),
    ],
)
def test_create_cross_field_errors(
    client: TestClient, overrides: dict[str, Any], message: str
) -> None:
    response = client.post("/events", json=event_payload(**overrides))

    assert response.status_code == 422
    assert response.json() == {"detail": message}


def test_get_unknown_event_is_404(client: TestClient) -> None:
    response = client.get("/events/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404
    assert response.json() == {"detail": "event not found"}


def test_invalid_uuid_is_422(client: TestClient) -> None:
    assert client.get("/events/not-a-uuid").status_code == 422


def test_list_filters_by_status_and_pages(client: TestClient, db: Conn) -> None:
    ids = [create_event(client, title=f"{MARK} List {n}")["id"] for n in range(3)]
    force_status(db, ids[0], "in_review")
    force_status(db, ids[1], "in_review")

    in_review = client.get("/events", params={"status": "in_review"}).json()
    both = client.get("/events", params=[("status", "in_review"), ("status", "draft")]).json()
    page = client.get("/events", params={"status": "in_review", "limit": 1, "offset": 1}).json()
    past_end = client.get("/events", params={"status": "in_review", "offset": 50}).json()

    assert {item["id"] for item in in_review["items"]} >= set(ids[:2])
    assert all(item["status"] == "in_review" for item in in_review["items"])
    assert set(ids) <= {item["id"] for item in both["items"]}
    assert page["limit"] == 1
    assert page["offset"] == 1
    assert len(page["items"]) == 1
    assert page["total"] == in_review["total"]
    assert past_end["items"] == []
    assert past_end["total"] == in_review["total"]


def test_list_rejects_bad_parameters(client: TestClient) -> None:
    assert client.get("/events", params={"status": "bogus"}).status_code == 422
    assert client.get("/events", params={"limit": 0}).status_code == 422
    assert client.get("/events", params={"limit": 201}).status_code == 422


def test_list_upcoming_and_closing_filters(client: TestClient, db: Conn) -> None:
    upcoming = create_event(client, title=f"{MARK} Soon", application_deadline=days_from_today(3))
    past = create_event(
        client,
        title=f"{MARK} Past",
        start_date=days_from_today(-10),
        end_date=days_from_today(-9),
        application_deadline=days_from_today(-20),
    )
    draft = create_event(client, title=f"{MARK} Draft", application_deadline=days_from_today(3))
    for event in (upcoming, past):
        force_status(db, event["id"], "published")

    upcoming_ids = {e["id"] for e in client.get("/events?upcoming=true&limit=200").json()["items"]}
    closing_ids = {
        e["id"] for e in client.get("/events?closing_within_days=7&limit=200").json()["items"]
    }

    assert upcoming["id"] in upcoming_ids
    assert past["id"] not in upcoming_ids
    assert draft["id"] not in upcoming_ids  # only published events count
    assert closing_ids & {upcoming["id"], past["id"], draft["id"]} == {upcoming["id"]}


# --- update -------------------------------------------------------------------------


def test_patch_changes_only_sent_fields(
    client: TestClient, revalidator: RecordingRevalidator
) -> None:
    event = create_event(client)

    response = client.patch(
        f"/events/{event['id']}",
        json={"city": None, "official_url": "https://www.pytest-m3.example.com/new/"},
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["city"] is None
    assert updated["official_url_normalized"] == "pytest-m3.example.com/new"
    assert updated["summary"] == event["summary"]
    assert updated["slug"] == event["slug"]  # the slug never changes
    assert updated["updated_at"] >= event["updated_at"]
    assert revalidator.calls == []  # drafts are not on the public site


def test_patch_rejects_null_for_required_fields_and_merged_inconsistency(
    client: TestClient,
) -> None:
    event = create_event(client)

    null_title = client.patch(f"/events/{event['id']}", json={"title": None})
    bad_dates = client.patch(f"/events/{event['id']}", json={"end_date": days_from_today(1)})

    assert null_title.status_code == 422
    assert "cannot be null: title" in null_title.text
    assert bad_dates.status_code == 422
    assert bad_dates.json() == {"detail": "end_date is before start_date"}


def test_patch_unknown_event_is_404(client: TestClient) -> None:
    response = client.patch("/events/00000000-0000-0000-0000-000000000000", json={"city": "X"})

    assert response.status_code == 404


def test_verification_status_sets_verified_at(client: TestClient) -> None:
    event = create_event(client)

    verified = client.patch(f"/events/{event['id']}", json={"verification_status": "verified"})
    unverified = client.patch(f"/events/{event['id']}", json={"verification_status": "unverified"})

    assert verified.json()["verified_at"] is not None
    assert unverified.json()["verified_at"] is None


def test_editing_a_published_event_revalidates_and_keeps_it_publishable(
    client: TestClient, db: Conn, revalidator: RecordingRevalidator
) -> None:
    event = create_event(client)
    force_status(db, event["id"], "published")

    edited = client.patch(f"/events/{event['id']}", json={"summary": "New summary."})
    broken = client.patch(f"/events/{event['id']}", json={"summary": None})

    assert edited.status_code == 200
    assert edited.json()["status"] == "published"
    assert revalidator.calls == [["events", f"event:{event['slug']}"]]
    assert broken.status_code == 422
    assert broken.json() == {
        "detail": "published events must stay publishable: summary is required"
    }


# --- state machine ------------------------------------------------------------------


@pytest.mark.parametrize("action", ALL_ACTIONS)
@pytest.mark.parametrize("status", ALL_STATUSES)
def test_every_action_from_every_status(
    client: TestClient, db: Conn, status: EventStatus, action: EventAction
) -> None:
    event = create_event(client)
    force_status(db, event["id"], status)
    sources, target = TRANSITIONS[action]

    response = transition(client, event["id"], action, reason="Pytest reason")

    if status in sources:
        assert response.status_code == 200, response.text
        assert response.json()["status"] == target
    else:
        assert response.status_code == 409
        assert response.json() == {"detail": f"cannot {action} an event in status {status}"}
        assert client.get(f"/events/{event['id']}").json()["status"] == status


@pytest.mark.parametrize("status", ALL_STATUSES)
def test_allowed_actions_match_the_transition_table(
    client: TestClient, db: Conn, status: EventStatus
) -> None:
    event = create_event(client)
    force_status(db, event["id"], status)

    allowed = client.get(f"/events/{event['id']}").json()["allowed_actions"]

    assert allowed == [action for action, (sources, _) in TRANSITIONS.items() if status in sources]


def test_full_lifecycle(client: TestClient, revalidator: RecordingRevalidator) -> None:
    event = create_event(client)
    event_id, tags = event["id"], ["events", f"event:{event['slug']}"]

    assert transition(client, event_id, "submit").json()["status"] == "in_review"
    assert transition(client, event_id, "approve").json()["status"] == "approved"
    assert revalidator.calls == []

    published = transition(client, event_id, "publish").json()
    assert published["status"] == "published"
    assert published["published_at"] is not None
    assert published["allowed_actions"] == ["unpublish", "archive"]
    assert revalidator.calls == [tags]

    assert transition(client, event_id, "unpublish").json()["status"] == "approved"
    assert revalidator.calls == [tags, tags]

    archived = transition(client, event_id, "archive").json()
    assert archived["status"] == "archived"
    assert archived["archived_at"] is not None
    assert revalidator.calls == [tags, tags]  # it was not public any more

    reopened = transition(client, event_id, "reopen").json()
    assert reopened["status"] == "draft"
    assert reopened["archived_at"] is None


def test_archiving_a_published_event_revalidates(
    client: TestClient, db: Conn, revalidator: RecordingRevalidator
) -> None:
    event = create_event(client)
    force_status(db, event["id"], "published")

    assert transition(client, event["id"], "archive").json()["status"] == "archived"
    assert revalidator.calls == [["events", f"event:{event['slug']}"]]


def test_submit_requires_fields(client: TestClient) -> None:
    event = create_event(client, summary=None, format=None, start_date=None, end_date=None)

    response = transition(client, event["id"], "submit")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "cannot submit: summary is required; start_date is required; format is required"
    }


@pytest.mark.parametrize(
    ("changes", "problem"),
    [
        ({"application_deadline": days_from_today(40)}, "application_deadline is after end_date"),
        (
            {"end_date": None, "application_deadline": days_from_today(35)},
            "application_deadline is after start_date",
        ),
        ({"official_url": "http://localhost/event"}, "official_url must point to a public host"),
        ({"official_url": "http://10.0.0.1/event"}, "official_url must point to a public host"),
        ({"official_url": "https://example.com:8443/e"}, "only ports 80 and 443"),
        ({"official_url": "https://intranet/e"}, "fully qualified host name"),
    ],
)
def test_approve_guards(
    client: TestClient, db: Conn, changes: dict[str, Any], problem: str
) -> None:
    event = create_event(client, **changes)
    force_status(db, event["id"], "in_review")

    response = transition(client, event["id"], "approve")

    assert response.status_code == 409
    assert response.json()["detail"].startswith("cannot approve: ")
    assert problem in response.json()["detail"]


def test_publish_rechecks_the_guards(client: TestClient, db: Conn) -> None:
    event = create_event(client, application_deadline=days_from_today(40))
    force_status(db, event["id"], "approved")

    response = transition(client, event["id"], "publish")

    assert response.status_code == 409
    assert "application_deadline is after end_date" in response.json()["detail"]


def test_reject_requires_a_reason_and_appends_it_to_internal_notes(
    client: TestClient, db: Conn
) -> None:
    event = create_event(client, internal_notes="Existing note.")
    force_status(db, event["id"], "in_review")

    missing = transition(client, event["id"], "reject")
    rejected = transition(client, event["id"], "reject", reason="Not a hackathon.")

    assert missing.status_code == 422
    assert missing.json() == {"detail": "reason is required to reject an event"}
    assert rejected.status_code == 200
    notes = rejected.json()["internal_notes"]
    assert notes.startswith("Existing note.\n[")
    assert notes.endswith("] reject: Not a hackathon.")


def test_transition_rejects_unknown_action(client: TestClient) -> None:
    event = create_event(client)

    assert transition(client, event["id"], "delete").status_code == 422


def test_transition_unknown_event_is_404(client: TestClient) -> None:
    response = transition(client, "00000000-0000-0000-0000-000000000000", "submit")

    assert response.status_code == 404

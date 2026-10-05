from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from fhc_api.db import Conn
from tests.factories import (
    create_event,
    days_from_today,
    force_status,
    insert_community_application,
    insert_team_application,
)


def overview(client: TestClient) -> dict[str, Any]:
    response = client.get("/overview")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def test_counts_change_with_the_data(client: TestClient, db: Conn) -> None:
    before = overview(client)

    in_review = create_event(client)
    force_status(db, in_review["id"], "in_review")
    closing = create_event(client, application_deadline=days_from_today(5))
    force_status(db, closing["id"], "published")
    later = create_event(client, application_deadline=days_from_today(20))
    force_status(db, later["id"], "published")
    ended = create_event(
        client,
        start_date=days_from_today(-3),
        end_date=days_from_today(-2),
        application_deadline=days_from_today(-10),
    )
    force_status(db, ended["id"], "published")
    in_progress = create_event(  # started yesterday, ends tomorrow: still upcoming
        client,
        start_date=days_from_today(-1),
        end_date=days_from_today(1),
        application_deadline=days_from_today(-5),
    )
    force_status(db, in_progress["id"], "published")
    insert_community_application(db)
    insert_community_application(db, status="contacted")
    insert_team_application(db)

    after = overview(client)

    assert after["in_review"] - before["in_review"] == 1
    assert after["published_upcoming"] - before["published_upcoming"] == 3
    assert after["closing_within_7_days"] - before["closing_within_7_days"] == 1
    assert after["new_community_applications"] - before["new_community_applications"] == 1
    assert after["new_team_applications"] - before["new_team_applications"] == 1


def test_heartbeats(client: TestClient, db: Conn) -> None:
    db.execute("delete from app.heartbeats")
    assert overview(client)["heartbeats"] == [
        {"source": "vercel_cron", "last_seen_at": None, "stale": True},
        {"source": "github_actions", "last_seen_at": None, "stale": True},
    ]

    now = datetime.now(UTC)
    db.execute(
        "insert into app.heartbeats (source, last_seen_at) values"
        " ('vercel_cron', %s), ('github_actions', %s)",
        (now - timedelta(hours=1), now - timedelta(hours=49)),
    )

    beats = {beat["source"]: beat for beat in overview(client)["heartbeats"]}
    assert beats["vercel_cron"]["stale"] is False
    assert beats["github_actions"]["stale"] is True
    assert beats["github_actions"]["last_seen_at"] is not None


def test_system_db_check(client: TestClient) -> None:
    response = client.get("/system/db")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["role"] == "admin_backend"
    assert body["latency_ms"] >= 0

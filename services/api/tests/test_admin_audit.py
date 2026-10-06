"""Admin UI decisions are audited in app.admin_actions (V1.1b acceptance 7)."""

from typing import Any

from fastapi.testclient import TestClient

from fhc_api.db import Conn
from tests.factories import create_event, insert_community_application, insert_team_application


def audit_rows(db: Conn, entity_id: object) -> list[dict[str, Any]]:
    return db.execute(
        "select actor, action, entity_type, detail from app.admin_actions"
        # `at` is constant inside the test transaction; order by the state change instead.
        " where entity_id = %s order by detail->>'to' = 'in_review' desc, action",
        (entity_id,),
    ).fetchall()


def test_event_transitions_are_audited(client: TestClient, db: Conn) -> None:
    event = create_event(client)
    client.post(f"/events/{event['id']}/transitions", json={"action": "submit"})
    client.post(
        f"/events/{event['id']}/transitions", json={"action": "reject", "reason": "personal note"}
    )
    assert audit_rows(db, event["id"]) == [
        {
            "actor": "admin_ui",
            "action": "submit",
            "entity_type": "event",
            "detail": {"from": "draft", "to": "in_review", "reason": False},
        },
        {
            "actor": "admin_ui",
            "action": "reject",
            "entity_type": "event",
            "detail": {"from": "in_review", "to": "rejected", "reason": True},
        },
    ]


def test_failed_transition_is_not_audited(client: TestClient, db: Conn) -> None:
    event = create_event(client)
    response = client.post(f"/events/{event['id']}/transitions", json={"action": "publish"})
    assert response.status_code == 409
    assert audit_rows(db, event["id"]) == []


def test_application_status_changes_are_audited(client: TestClient, db: Conn) -> None:
    community = insert_community_application(db)
    team = insert_team_application(db)
    assert (
        client.patch(f"/community-applications/{community['id']}", json={"status": "contacted"})
    ).status_code == 200
    assert (
        client.patch(f"/team-applications/{team['id']}", json={"status": "spam"})
    ).status_code == 200
    assert audit_rows(db, community["id"]) == [
        {
            "actor": "admin_ui",
            "action": "set_status",
            "entity_type": "community_application",
            "detail": {"from": "new", "to": "contacted"},
        }
    ]
    assert audit_rows(db, team["id"])[0]["detail"] == {"from": "new", "to": "spam"}


def test_unknown_application_is_404_and_not_audited(client: TestClient) -> None:
    response = client.patch(
        "/community-applications/00000000-0000-0000-0000-000000000000", json={"status": "spam"}
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "community application not found"}

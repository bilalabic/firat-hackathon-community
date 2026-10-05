"""Test data helpers. Every row is marked with MARK (see conftest)."""

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient

from fhc_api.common.clock import today_in
from fhc_api.common.sql import insert_row
from fhc_api.db import Conn
from tests.conftest import MARK


def days_from_today(days: int, timezone: str = "Europe/Istanbul") -> str:
    return (today_in(timezone) + timedelta(days=days)).isoformat()


def event_payload(**overrides: Any) -> dict[str, Any]:
    """A complete event that passes every guard."""
    return {
        "title": f"{MARK} Hackathon",
        "summary": "A weekend hackathon.",
        "official_url": "https://pytest-m3.example.com/hackathon",
        "application_url": "https://pytest-m3.example.com/apply",
        "start_date": days_from_today(30),
        "end_date": days_from_today(31),
        "application_deadline": days_from_today(20),
        "format": "in_person",
        "city": "Elazığ",
        "country": "TR",
        **overrides,
    }


def create_event(client: TestClient, **overrides: Any) -> dict[str, Any]:
    response = client.post("/events", json=event_payload(**overrides))
    assert response.status_code == 201, response.text
    event: dict[str, Any] = response.json()
    return event


def force_status(db: Conn, event_id: str, status: str) -> None:
    """Put an event straight into a status (setup only; bypasses the state machine)."""
    db.execute(
        "update app.events set status = %(status)s::app.event_status,"
        " published_at = case when %(status)s::app.event_status = 'published'"
        " then now() else published_at end"
        " where id = %(id)s",
        {"status": status, "id": event_id},
    )


def insert_community_application(db: Conn, **overrides: Any) -> dict[str, Any]:
    values = {
        "full_name": f"{MARK} Applicant",
        "preferred_channel": "telegram",
        "telegram_username": "pytest_m3_user",
        "consent_version": "test-v1",
        **overrides,
    }
    return dict(insert_row(db, "community_applications", values))


def insert_team_application(db: Conn, **overrides: Any) -> dict[str, Any]:
    values = {
        "full_name": f"{MARK} Contributor",
        "areas": ["backend"],
        "consent_version": "test-v1",
        **overrides,
    }
    return dict(insert_row(db, "team_applications", values))

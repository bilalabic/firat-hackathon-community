"""Admin bot wiring (status endpoint, defaults, misconfiguration) and an end-to-end run of
the real background thread against the fake Bot API."""

import logging
import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from fhc_api.admin_bot import outbox
from fhc_api.admin_bot.runner import AdminBotRunner
from fhc_api.admin_bot.settings import AdminBotConfig
from fhc_api.db import Conn
from fhc_api.main import create_app
from tests.conftest import AUTH, BASE_URL, LOCAL_DATABASE_URL, RecordingRevalidator, make_settings
from tests.factories import create_event, insert_community_application
from tests.fake_telegram import (
    ADMIN_ID,
    ADMIN_LEAK_MARKER,
    ADMIN_TOKEN,
    STRANGER_ID,
    FakeTelegram,
    buttons,
)

BOT_ENV = {
    "TELEGRAM_ADMIN_ENABLED": "true",
    "TELEGRAM_ADMIN_BOT_TOKEN": ADMIN_TOKEN,
    "TELEGRAM_ADMIN_USER_IDS": str(ADMIN_ID),
}


def status_of(app_client: TestClient) -> dict[str, Any]:
    response = app_client.get("/admin-bot/status")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_disabled_by_default_and_never_calls_telegram() -> None:
    fake = FakeTelegram()
    app = create_app(make_settings(), admin_bot_client=fake.client())
    with TestClient(app, base_url=BASE_URL, headers=AUTH) as app_client:
        body = status_of(app_client)
        assert app_client.get("/health").status_code == 200
    assert body["enabled"] is False
    assert body["state"] == "disabled"
    assert body["running"] is False
    assert body["pending_notifications"] is None
    assert fake.calls == []


def test_status_requires_the_token() -> None:
    app = create_app(make_settings())
    assert TestClient(app, base_url=BASE_URL).get("/admin-bot/status").status_code == 401


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"TELEGRAM_ADMIN_USER_IDS": None}, "TELEGRAM_ADMIN_USER_IDS is empty"),
        ({"TELEGRAM_ADMIN_BOT_TOKEN": "not-a-token"}, "invalid format"),
        ({"TELEGRAM_ADMIN_BOT_TOKEN": None}, "is not set"),
        ({"TELEGRAM_ADMIN_SCAN_INTERVAL_S": "fast"}, "TELEGRAM_ADMIN_SCAN_INTERVAL_S"),
    ],
)
def test_misconfiguration_disables_only_the_bot(
    overrides: dict[str, Any], message: str, caplog: pytest.LogCaptureFixture
) -> None:
    fake = FakeTelegram()
    settings = make_settings(**{**BOT_ENV, **overrides})
    # An injected client would skip the token format check; inject only when not testing it.
    injected = None if "TELEGRAM_ADMIN_BOT_TOKEN" in overrides else fake.client()
    with caplog.at_level(logging.WARNING):
        app = create_app(settings, admin_bot_client=injected)
    # No lifespan here (the pool would wait for the unused database on shutdown);
    # `start()` is a no-op without a runner, which test_disabled_... covers with a lifespan.
    app_client = TestClient(app, base_url=BASE_URL, headers=AUTH)
    assert app_client.get("/health").status_code == 200
    body = status_of(app_client)
    assert app.state.admin_bot.runner is None
    assert body["state"] == "config_error"
    assert message in body["config_error"]
    assert fake.calls == []
    assert any("admin bot not started" in record.getMessage() for record in caplog.records)
    assert all(ADMIN_LEAK_MARKER not in record.getMessage() for record in caplog.records)


def local_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL", LOCAL_DATABASE_URL)
    try:
        psycopg.connect(url, connect_timeout=3).close()
    except psycopg.OperationalError:
        pytest.skip("local Supabase Postgres is not running (pnpm db:start)")
    return url


def wait_for(condition: Callable[[], bool], timeout_s: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.02)
    raise AssertionError("condition not met in time")


def test_lifespan_starts_and_stops_the_thread_and_reports_errors() -> None:
    """The thread runs against the local database pool. The fake has no updates and the
    scan finds nothing new, so nothing is written."""
    fake = FakeTelegram(long_poll_s=0.05)
    settings = make_settings(DATABASE_URL=local_database_url(), **BOT_ENV)
    app = create_app(settings, admin_bot_client=fake.client())
    with TestClient(app, base_url=BASE_URL, headers=AUTH) as app_client:
        wait_for(lambda: len(fake.bodies("getUpdates")) >= 2)
        body = status_of(app_client)
        assert body["state"] == "running"
        assert body["running"] is True
        assert body["bot_username"] == "fhc_admin_bot"
        assert body["allowlist_size"] == 1
        assert body["last_poll_at"] is not None and body["last_scan_at"] is not None
        assert isinstance(body["pending_notifications"], int)

        # Telegram becomes unreachable: the API stays up, the bot reports and backs off.
        import httpx2

        fake.failures["getUpdates"] = httpx2.Response(
            502, json={"ok": False, "error_code": 502, "description": "Bad Gateway"}
        )
        wait_for(lambda: status_of(app_client)["state"] == "error")
        body = status_of(app_client)
        assert "getUpdates failed: 502" in body["last_error"]
        assert ADMIN_LEAK_MARKER not in str(body)
        assert app_client.get("/health").status_code == 200
        started = time.monotonic()
    # Shutdown (TestClient exit) stopped the thread promptly, even during a backoff wait.
    assert time.monotonic() - started < 5
    assert app.state.admin_bot.runner.running is False


# --- end-to-end with the real thread -------------------------------------------------


def start_runner(db: Conn, fake: FakeTelegram, revalidator: RecordingRevalidator) -> AdminBotRunner:
    @contextmanager
    def open_conn() -> Iterator[Conn]:
        with db.transaction():
            yield db

    config = AdminBotConfig(
        token=SecretStr(ADMIN_TOKEN), admin_ids=frozenset({ADMIN_ID}), scan_interval_s=10
    )
    runner = AdminBotRunner(config, fake.client(), open_conn, revalidator)
    runner.start()
    return runner


def test_end_to_end_with_the_background_thread(
    client: TestClient,
    db: Conn,
    revalidator: RecordingRevalidator,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Submitted event -> one review message; approve -> approved + publish prompt;
    publish -> confirm -> published (revalidation); stale press refused; foreign user
    ignored; application message without personal data; restart -> no duplicates.

    The main thread touches the shared test connection only while the runner is stopped
    (the runner thread owns it while running)."""
    monkeypatch.setattr(outbox, "SEND_PACING_S", 0.0)
    fake = FakeTelegram(long_poll_s=0.02)
    event = create_event(client)
    client.post(f"/events/{event['id']}/transitions", json={"action": "submit"})
    application = insert_community_application(db, full_name="Pytest M3 Elif Şahin")
    event_hex, app_hex = UUID(event["id"]).hex, application["id"].hex

    def sent(entity_hex: str) -> list[dict[str, Any]]:
        return fake.sent_about(entity_hex)

    def message_id(body: dict[str, Any]) -> int:
        return 100 + fake.bodies("sendMessage").index(body)

    with caplog.at_level(logging.DEBUG):
        runner = start_runner(db, fake, revalidator)
        try:
            wait_for(lambda: len(sent(event_hex)) == 1 and len(sent(app_hex)) == 1)
            review = sent(event_hex)[0]
            app_text = sent(app_hex)[0]["text"]

            fake.press(buttons(review)["✅ Approve"], message_id(review), user_id=STRANGER_ID)
            fake.press(buttons(review)["✅ Approve"], message_id(review))
            wait_for(lambda: len(sent(event_hex)) == 2)  # the publish prompt
            prompt = sent(event_hex)[1]

            # A second press on the (now decided) review message is refused.
            fake.press(buttons(review)["✅ Approve"], message_id(review))
            fake.press(buttons(prompt)["🚀 Publish"], message_id(prompt))
            wait_for(lambda: len(fake.bodies("editMessageReplyMarkup")) == 1)
            confirm = fake.bodies("editMessageReplyMarkup")[0]
            fake.press(buttons(confirm)["🚀 Confirm publish"], message_id(prompt))
            wait_for(lambda: "🚀 Published" in fake.answers())
        finally:
            runner.stop()
    assert not runner.running

    assert fake.answers() == [
        "Not allowed.",
        "✅ Approved",
        "Already handled (approved).",
        "Confirm to publish on the public site.",
        "🚀 Published",
    ]
    published = client.get(f"/events/{event['id']}").json()
    assert published["status"] == "published"
    assert revalidator.calls == [["events", f"event:{published['slug']}"]]
    assert "Pytest" in app_text and "Elif" not in app_text and "Şahin" not in app_text
    assert "pytest_m3_user" not in app_text
    actors = db.execute(
        "select actor, action from app.admin_actions where entity_id = %s order by action",
        (event["id"],),
    ).fetchall()
    assert actors == [
        {"actor": "telegram:1111", "action": "approve"},
        {"actor": "telegram:1111", "action": "publish"},
        {"actor": "admin_ui", "action": "submit"},
    ]

    # Restart: a new thread scans again and sends nothing new.
    sends_before = len(fake.bodies("sendMessage"))
    polls_before = len(fake.bodies("getUpdates"))
    runner = start_runner(db, fake, revalidator)
    try:
        wait_for(lambda: len(fake.bodies("getUpdates")) > polls_before + 1)
    finally:
        runner.stop()
    assert len(fake.bodies("sendMessage")) == sends_before
    assert all(ADMIN_LEAK_MARKER not in record.getMessage() for record in caplog.records)

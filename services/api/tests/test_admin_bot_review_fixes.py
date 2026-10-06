"""Admin bot: re-notification of re-opened applications, server-side confirmation, scan
expiry, poison updates, database error classes and reply edge cases."""

from typing import Any
from uuid import UUID

import psycopg
import pytest
from fastapi.testclient import TestClient

from fhc_api.admin_bot import codec, outbox
from fhc_api.admin_bot.runner import MAX_UPDATE_ATTEMPTS, AdminBotRunner
from fhc_api.common.sql import insert_row
from fhc_api.db import Conn
from fhc_api.telegram.client import TelegramUpdate
from tests.conftest import MARK, RecordingRevalidator
from tests.fake_telegram import ADMIN_ID, OTHER_ADMIN_ID, STRANGER_ID, FakeTelegram, buttons
from tests.test_admin_bot_flow import (
    get_event,
    in_review,
    make_runner,
    message_id_of,
    notifications,
    only_message,
)


@pytest.fixture(autouse=True)
def _no_pacing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(outbox, "SEND_PACING_S", 0.0)


@pytest.fixture
def fake() -> FakeTelegram:
    return FakeTelegram()


@pytest.fixture
def runner(db: Conn, fake: FakeTelegram, revalidator: RecordingRevalidator) -> AdminBotRunner:
    return make_runner(db, fake, revalidator)


def offset(db: Conn) -> int | None:
    row = db.execute(
        "select value from app.bot_state where key = 'admin_bot.987654321.update_offset'"
    ).fetchone()
    return int(row["value"]) if row else None


# --- 1. re-opened applications ------------------------------------------------------


def test_application_set_back_to_new_is_notified_again(
    client: TestClient, db: Conn, fake: FakeTelegram, runner: AdminBotRunner
) -> None:
    # `now()` is constant inside the test transaction, so the application starts with an
    # older updated_at (inserts do not run the trigger); later updates set it to now().
    hour_ago = db.execute("select now() - interval '1 hour' as t").fetchone()
    assert hour_ago is not None
    values = {
        "full_name": f"{MARK} Applicant",
        "preferred_channel": "telegram",
        "telegram_username": "pytest_m3_user",
        "consent_version": "test-v1",
        "updated_at": hour_ago["t"],
    }
    application = dict(insert_row(db, "community_applications", values))
    entity_hex = application["id"].hex
    runner.scan()
    assert len(fake.sent_about(entity_hex)) == 1

    url = f"/community-applications/{application['id']}"
    assert client.patch(url, json={"status": "contacted"}).status_code == 200
    runner.scan()  # retires the first message
    assert client.patch(url, json={"status": "new"}).status_code == 200
    runner.scan()
    assert len(fake.sent_about(entity_hex)) == 2
    assert [n["resolution"] for n in notifications(db, str(application["id"]))] == [
        "superseded",
        None,
    ]


# --- 4. server-side two-step confirmation -------------------------------------------


def approved_with_prompt(
    client: TestClient, fake: FakeTelegram, runner: AdminBotRunner
) -> tuple[dict[str, Any], dict[str, Any]]:
    event = in_review(client)
    client.post(f"/events/{event['id']}/transitions", json={"action": "approve"})
    runner.scan()
    return event, only_message(fake, event["id"])


def crafted(prompt: dict[str, Any], action: codec.Action) -> str:
    """A well-formed button the bot never showed (same entity and token)."""
    original = codec.decode(next(iter(buttons(prompt).values())))
    assert original is not None
    return codec.encode(
        codec.Callback(action, original.entity_type, original.entity_id, original.token)
    )


def test_crafted_publish_confirm_without_the_first_press_is_refused(
    client: TestClient, fake: FakeTelegram, runner: AdminBotRunner
) -> None:
    event, prompt = approved_with_prompt(client, fake, runner)
    fake.press(crafted(prompt, "publish_confirm"), message_id_of(fake, prompt))
    runner.poll_once(0)
    assert get_event(client, event["id"])["status"] == "approved"
    assert str(fake.answers()[-1]).startswith("Press the button again")
    restored = fake.bodies("editMessageReplyMarkup")[-1]
    assert list(buttons(restored)) == ["🚀 Publish", "Later"]


def test_crafted_reject_confirm_without_the_first_press_is_refused(
    client: TestClient, db: Conn, fake: FakeTelegram, runner: AdminBotRunner
) -> None:
    event = in_review(client)
    runner.scan()
    review = only_message(fake, event["id"])
    sends = len(fake.bodies("sendMessage"))
    fake.press(crafted(review, "reject_confirm"), message_id_of(fake, review))
    runner.poll_once(0)
    assert get_event(client, event["id"])["status"] == "in_review"
    assert len(fake.bodies("sendMessage")) == sends  # no reason prompt
    assert db.execute("select count(*) as n from app.bot_pending_replies").fetchone() == {"n": 0}


def test_confirm_must_follow_the_first_press_quickly(
    client: TestClient, db: Conn, fake: FakeTelegram, runner: AdminBotRunner
) -> None:
    event, prompt = approved_with_prompt(client, fake, runner)
    fake.press(buttons(prompt)["🚀 Publish"], message_id_of(fake, prompt))
    runner.poll_once(0)
    db.execute("update app.bot_notifications set confirm_at = now() - interval '11 minutes'")
    fake.press(crafted(prompt, "publish_confirm"), message_id_of(fake, prompt))
    runner.poll_once(0)
    assert get_event(client, event["id"])["status"] == "approved"
    assert str(fake.answers()[-1]).startswith("Press the button again")


# --- 6. scan expiry -----------------------------------------------------------------


def test_scan_expires_old_unpressed_messages_and_sends_a_fresh_one(
    client: TestClient, db: Conn, fake: FakeTelegram, runner: AdminBotRunner
) -> None:
    event = in_review(client)
    runner.scan()
    first = only_message(fake, event["id"])
    db.execute(
        "update app.bot_notifications set sent_at = now() - interval '13 hours'"
        " where entity_id = %s",
        (event["id"],),
    )
    runner.scan()
    edit = fake.bodies("editMessageText")[-1]
    assert edit["message_id"] == message_id_of(fake, first)
    assert "Buttons expired after 12 h; a fresh message follows." in edit["text"]
    assert len(fake.sent_about(UUID(event["id"]).hex)) == 2
    assert [n["resolution"] for n in notifications(db, event["id"])] == ["expired", None]
    pending = db.execute(
        "select count(*) as n from app.bot_notifications"
        " where entity_id = %s and resolved_at is null and message_id is not null",
        (event["id"],),
    ).fetchone()
    assert pending == {"n": 1}  # "Awaiting decision" counts the fresh message only


# --- 2. poison updates and database errors --------------------------------------------


def test_a_malformed_update_is_skipped_and_confirmed(
    db: Conn, fake: FakeTelegram, runner: AdminBotRunner
) -> None:
    fake.updates.append({"update_id": 1, "callback_query": {"id": "x", "data": "y"}})  # no from
    fake.updates.append({"no_update_id": True})
    start_id = fake.reply("/start", 1)
    assert runner.poll_once(0) == 2
    assert "FHC admin bot" in fake.bodies("sendMessage")[-1]["text"]
    assert offset(db) == start_id + 1


def raise_in_handler(runner: AdminBotRunner, exc: Exception) -> list[int]:
    calls: list[int] = []

    def handle(update: TelegramUpdate) -> None:
        calls.append(update.update_id)
        raise exc

    runner._handlers.handle = handle  # type: ignore[method-assign]
    return calls


def test_a_statement_error_does_not_block_the_queue(
    db: Conn, fake: FakeTelegram, runner: AdminBotRunner
) -> None:
    raise_in_handler(runner, psycopg.errors.QueryCanceled("canceling statement"))
    update_id = fake.reply("/start", 1)
    assert runner.poll_once(0) == 1
    assert offset(db) == update_id + 1
    assert runner.last_error is not None and "QueryCanceled" in runner.last_error


def test_a_connection_error_is_retried_then_skipped(
    db: Conn, fake: FakeTelegram, runner: AdminBotRunner
) -> None:
    calls = raise_in_handler(runner, psycopg.OperationalError("connection lost"))
    update_id = fake.reply("/start", 1)
    for _ in range(MAX_UPDATE_ATTEMPTS - 1):
        with pytest.raises(psycopg.OperationalError):
            runner.poll_once(0)
        assert offset(db) is None  # not confirmed: retried later
    assert runner.poll_once(0) == 1  # gives up after MAX_UPDATE_ATTEMPTS
    assert calls == [update_id] * MAX_UPDATE_ATTEMPTS
    assert offset(db) == update_id + 1


# --- 8. reason replies ----------------------------------------------------------------


def reason_prompt(
    client: TestClient, fake: FakeTelegram, runner: AdminBotRunner
) -> tuple[str, int]:
    event = in_review(client)
    runner.scan()
    review = only_message(fake, event["id"])
    fake.press(buttons(review)["✏️ Request changes"], message_id_of(fake, review))
    runner.poll_once(0)
    prompt = fake.bodies("sendMessage")[-1]
    assert prompt["reply_markup"]["force_reply"] is True
    return event["id"], message_id_of(fake, prompt)


def test_replies_from_another_chat_or_user_do_not_use_the_prompt(
    client: TestClient, db: Conn, fake: FakeTelegram, revalidator: RecordingRevalidator
) -> None:
    runner = make_runner(db, fake, revalidator, admins=frozenset({ADMIN_ID, OTHER_ADMIN_ID}))
    event = in_review(client)
    runner.scan()
    mine = next(b for b in fake.sent_about(UUID(event["id"]).hex) if b["chat_id"] == ADMIN_ID)
    fake.press(buttons(mine)["✏️ Request changes"], message_id_of(fake, mine))
    runner.poll_once(0)
    prompt_id = message_id_of(fake, fake.bodies("sendMessage")[-1])

    fake.reply("from the other admin", prompt_id, user_id=OTHER_ADMIN_ID)
    fake.reply("from a stranger", prompt_id, user_id=STRANGER_ID)
    runner.poll_once(0)
    assert get_event(client, event["id"])["status"] == "in_review"
    last = fake.bodies("sendMessage")[-1]
    assert last["chat_id"] == OTHER_ADMIN_ID and "FHC admin bot" in last["text"]  # help only
    assert db.execute("select count(*) as n from app.bot_pending_replies").fetchone() == {"n": 1}

    fake.reply("Add the deadline", prompt_id)  # the prompt still works for its own chat
    runner.poll_once(0)
    assert get_event(client, event["id"])["status"] == "draft"


def test_too_long_and_empty_reasons_keep_the_prompt_open(
    client: TestClient, db: Conn, fake: FakeTelegram, runner: AdminBotRunner
) -> None:
    event_id, prompt_id = reason_prompt(client, fake, runner)
    for text in ("x" * 1001, ""):
        fake.reply(text, prompt_id)
        runner.poll_once(0)
        assert "1-1000 characters" in fake.bodies("sendMessage")[-1]["text"]
    assert get_event(client, event_id)["status"] == "in_review"
    assert db.execute("select count(*) as n from app.bot_pending_replies").fetchone() == {"n": 1}
    fake.reply("x" * 1000, prompt_id)
    runner.poll_once(0)
    assert get_event(client, event_id)["status"] == "draft"


def test_a_reply_to_a_non_prompt_message_gets_help(
    client: TestClient, fake: FakeTelegram, runner: AdminBotRunner
) -> None:
    event_id, prompt_id = reason_prompt(client, fake, runner)
    fake.reply("is this the reason?", prompt_id - 1)  # replies to the review message
    runner.poll_once(0)
    assert "FHC admin bot" in fake.bodies("sendMessage")[-1]["text"]
    assert get_event(client, event_id)["status"] == "in_review"


# --- 5. shutdown during a scan ---------------------------------------------------------


def test_scan_stops_sending_once_shutdown_started(
    client: TestClient, fake: FakeTelegram, runner: AdminBotRunner
) -> None:
    event = in_review(client)
    runner._stop.set()  # as stop() does, before the thread notices
    assert runner.scan() == 0
    assert fake.sent_about(UUID(event["id"]).hex) == []

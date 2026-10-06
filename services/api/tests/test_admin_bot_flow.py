"""Admin bot integration: outbox scan and handlers against the local DB (rolled back) and
a fake Bot API (MockTransport). The runner's units of work are driven directly.

Note: inside one test transaction `now()` is constant, so an edit does not change
`updated_at`; "changed since the message" is exercised through status changes and
tampered tokens instead (the token itself is unit-tested).
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from fhc_api.admin_bot import outbox
from fhc_api.admin_bot.runner import AdminBotRunner
from fhc_api.admin_bot.settings import AdminBotConfig
from fhc_api.db import Conn
from tests.conftest import RecordingRevalidator
from tests.factories import create_event, insert_community_application, insert_team_application
from tests.fake_telegram import (
    ADMIN_ID,
    ADMIN_LEAK_MARKER,
    ADMIN_TOKEN,
    OTHER_ADMIN_ID,
    STRANGER_ID,
    FakeTelegram,
    buttons,
)


@pytest.fixture(autouse=True)
def _no_pacing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(outbox, "SEND_PACING_S", 0.0)


@pytest.fixture
def fake() -> FakeTelegram:
    return FakeTelegram()


def make_runner(
    db: Conn,
    fake: FakeTelegram,
    revalidator: RecordingRevalidator,
    *,
    admins: frozenset[int] = frozenset({ADMIN_ID}),
) -> AdminBotRunner:
    @contextmanager
    def open_conn() -> Iterator[Conn]:
        with db.transaction():
            yield db

    config = AdminBotConfig(token=SecretStr(ADMIN_TOKEN), admin_ids=admins)
    return AdminBotRunner(config, fake.client(), open_conn, revalidator)


@pytest.fixture
def runner(db: Conn, fake: FakeTelegram, revalidator: RecordingRevalidator) -> AdminBotRunner:
    return make_runner(db, fake, revalidator)


def in_review(client: TestClient, **overrides: Any) -> dict[str, Any]:
    event = create_event(client, **overrides)
    response = client.post(f"/events/{event['id']}/transitions", json={"action": "submit"})
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def get_event(client: TestClient, event_id: str) -> dict[str, Any]:
    return client.get(f"/events/{event_id}").json()  # type: ignore[no-any-return]


def only_message(fake: FakeTelegram, entity_id: str) -> dict[str, Any]:
    sent = fake.sent_about(UUID(entity_id).hex)
    assert len(sent) == 1, sent
    return sent[0]


def message_id_of(fake: FakeTelegram, body: dict[str, Any]) -> int:
    """The fake numbers messages in send order starting at 100."""
    return 100 + fake.bodies("sendMessage").index(body)


def actions(db: Conn, entity_id: str) -> list[dict[str, Any]]:
    """Ordered by actor (admin_ui first): `at` is constant inside the test transaction."""
    return db.execute(
        "select actor, action, detail from app.admin_actions"
        " where entity_id = %s order by actor, action",
        (entity_id,),
    ).fetchall()


def notifications(db: Conn, entity_id: str) -> list[dict[str, Any]]:
    """review before publish; within a kind, resolved before unresolved."""
    return db.execute(
        "select kind, chat_id, message_id, resolution from app.bot_notifications"
        " where entity_id = %s order by kind desc, resolution nulls last",
        (entity_id,),
    ).fetchall()


# --- outbox --------------------------------------------------------------------------


def test_event_in_review_is_sent_once_even_after_a_restart(
    client: TestClient,
    db: Conn,
    fake: FakeTelegram,
    revalidator: RecordingRevalidator,
    runner: AdminBotRunner,
) -> None:
    event = in_review(client, title="Pytest M3 <Bot> & Co")
    runner.scan()
    runner.scan()
    make_runner(db, fake, revalidator).scan()  # a restart

    body = only_message(fake, event["id"])
    assert body["chat_id"] == ADMIN_ID
    assert body["parse_mode"] == "HTML"
    assert "<b>Pytest M3 &lt;Bot&gt; &amp; Co</b>" in body["text"]
    assert "✓ Dates" in body["text"]
    assert list(buttons(body)) == ["✅ Approve", "✏️ Request changes", "⛔ Reject"]
    assert notifications(db, event["id"]) == [
        {
            "kind": "review",
            "chat_id": ADMIN_ID,
            "message_id": message_id_of(fake, body),
            "resolution": None,
        }
    ]


def test_every_admin_gets_a_message_and_one_decision_resolves_all(
    client: TestClient, db: Conn, fake: FakeTelegram, revalidator: RecordingRevalidator
) -> None:
    runner = make_runner(db, fake, revalidator, admins=frozenset({ADMIN_ID, OTHER_ADMIN_ID}))
    event = in_review(client)
    runner.scan()
    sent = fake.sent_about(UUID(event["id"]).hex)
    assert sorted(body["chat_id"] for body in sent) == [ADMIN_ID, OTHER_ADMIN_ID]

    mine = next(body for body in sent if body["chat_id"] == ADMIN_ID)
    fake.press(buttons(mine)["✅ Approve"], message_id_of(fake, mine))
    runner.poll_once(0)

    edited = {(b["chat_id"], b["message_id"]) for b in fake.bodies("editMessageText")}
    assert edited == {(b["chat_id"], message_id_of(fake, b)) for b in sent}
    assert all("Approved by telegram:1111" in b["text"] for b in fake.bodies("editMessageText"))
    assert "reply_markup" not in fake.bodies("editMessageText")[0]


def test_a_backlog_drains_over_several_scans(
    client: TestClient, fake: FakeTelegram, runner: AdminBotRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(outbox, "MAX_SENDS_PER_KIND", 1)
    first = in_review(client, title="Pytest M3 First")
    second = in_review(client, title="Pytest M3 Second")
    ids = {UUID(first["id"]).hex, UUID(second["id"]).hex}

    def ours() -> int:
        return sum(len(fake.sent_about(entity_hex)) for entity_hex in ids)

    runner.scan()
    assert ours() == 1
    runner.scan()
    assert ours() == 2  # the already-notified event no longer blocks the next one
    runner.scan()
    assert ours() == 2


def test_send_failure_releases_the_claim(
    client: TestClient, db: Conn, fake: FakeTelegram, runner: AdminBotRunner
) -> None:
    import httpx2

    event = in_review(client)
    fake.failures["sendMessage"] = httpx2.Response(
        400, json={"ok": False, "error_code": 400, "description": "Bad Request: chat not found"}
    )
    assert runner.scan() == 0
    assert notifications(db, event["id"]) == []
    del fake.failures["sendMessage"]
    assert runner.scan() >= 1
    assert len(notifications(db, event["id"])) == 1


def test_rate_limit_aborts_the_scan(
    client: TestClient, db: Conn, fake: FakeTelegram, runner: AdminBotRunner
) -> None:
    import httpx2

    from fhc_api.telegram.client import TelegramAPIError

    event = in_review(client)
    fake.failures["sendMessage"] = httpx2.Response(
        429,
        json={
            "ok": False,
            "error_code": 429,
            "description": "Too Many Requests",
            "parameters": {"retry_after": 3},
        },
    )
    with pytest.raises(TelegramAPIError) as info:
        runner.scan()
    assert info.value.retry_after == 3
    assert notifications(db, event["id"]) == []


# --- review flow ---------------------------------------------------------------------


def test_approve_then_publish_with_confirmation(
    client: TestClient,
    db: Conn,
    fake: FakeTelegram,
    revalidator: RecordingRevalidator,
    runner: AdminBotRunner,
) -> None:
    event = in_review(client)
    runner.scan()
    review = only_message(fake, event["id"])
    fake.press(buttons(review)["✅ Approve"], message_id_of(fake, review))
    assert runner.poll_once(0) == 1

    assert get_event(client, event["id"])["status"] == "approved"
    assert fake.answers() == ["✅ Approved"]
    assert [a["actor"] for a in actions(db, event["id"])] == ["admin_ui", "telegram:1111"]
    assert actions(db, event["id"])[1]["detail"] == {
        "from": "in_review",
        "to": "approved",
        "reason": False,
    }

    # The publish prompt follows in the next scan.
    runner.scan()
    prompt = fake.sent_about(UUID(event["id"]).hex)[1]
    assert list(buttons(prompt)) == ["🚀 Publish", "Later"]
    prompt_id = message_id_of(fake, prompt)

    fake.press(buttons(prompt)["🚀 Publish"], prompt_id)
    runner.poll_once(0)
    assert get_event(client, event["id"])["status"] == "approved"  # not yet: confirm first
    confirm = fake.bodies("editMessageReplyMarkup")[-1]
    assert confirm["message_id"] == prompt_id
    assert list(buttons(confirm)) == ["🚀 Confirm publish", "Cancel"]

    fake.press(buttons(confirm)["Cancel"], prompt_id)
    runner.poll_once(0)
    assert list(buttons(fake.bodies("editMessageReplyMarkup")[-1])) == ["🚀 Publish", "Later"]

    fake.press(buttons(confirm)["🚀 Confirm publish"], prompt_id)
    runner.poll_once(0)
    published = get_event(client, event["id"])
    assert published["status"] == "published"
    assert published["published_at"] is not None
    assert revalidator.calls == [["events", f"event:{published['slug']}"]]
    assert fake.answers()[-1] == "🚀 Published"
    assert notifications(db, event["id"])[1]["resolution"] == "published"


def test_reject_needs_confirmation_and_a_reason(
    client: TestClient, db: Conn, fake: FakeTelegram, runner: AdminBotRunner
) -> None:
    event = in_review(client)
    runner.scan()
    review = only_message(fake, event["id"])
    review_id = message_id_of(fake, review)

    fake.press(buttons(review)["⛔ Reject"], review_id)
    runner.poll_once(0)
    confirm = fake.bodies("editMessageReplyMarkup")[-1]
    assert list(buttons(confirm)) == ["⛔ Confirm reject", "Cancel"]
    assert get_event(client, event["id"])["status"] == "in_review"

    fake.press(buttons(confirm)["⛔ Confirm reject"], review_id)
    runner.poll_once(0)
    prompt = fake.bodies("sendMessage")[-1]
    assert prompt["reply_markup"]["force_reply"] is True
    assert prompt["reply_parameters"]["message_id"] == review_id
    prompt_id = message_id_of(fake, prompt)
    assert get_event(client, event["id"])["status"] == "in_review"

    fake.reply("   ", prompt_id)  # empty: the prompt stays open
    runner.poll_once(0)
    assert "1-1000 characters" in fake.bodies("sendMessage")[-1]["text"]

    fake.reply("Dates <are> wrong", prompt_id)
    runner.poll_once(0)
    rejected = get_event(client, event["id"])
    assert rejected["status"] == "rejected"
    assert rejected["internal_notes"].endswith("reject: Dates <are> wrong")
    assert actions(db, event["id"])[-1]["detail"] == {
        "from": "in_review",
        "to": "rejected",
        "reason": True,
    }
    assert fake.bodies("sendMessage")[-1]["text"] == "⛔ Rejected"
    assert db.execute("select count(*) as n from app.bot_pending_replies").fetchone() == {"n": 0}

    fake.reply("again", prompt_id)  # the prompt is used up: help text, nothing changes
    runner.poll_once(0)
    assert "FHC admin bot" in fake.bodies("sendMessage")[-1]["text"]


def test_request_changes_moves_the_event_back_to_draft(
    client: TestClient, db: Conn, fake: FakeTelegram, runner: AdminBotRunner
) -> None:
    event = in_review(client)
    runner.scan()
    review = only_message(fake, event["id"])
    fake.press(buttons(review)["✏️ Request changes"], message_id_of(fake, review))
    runner.poll_once(0)
    prompt_id = message_id_of(fake, fake.bodies("sendMessage")[-1])
    fake.reply("Add the deadline", prompt_id)
    runner.poll_once(0)
    draft = get_event(client, event["id"])
    assert draft["status"] == "draft"
    assert draft["internal_notes"].endswith("request_changes: Add the deadline")


def test_expired_prompt_is_refused(
    client: TestClient, db: Conn, fake: FakeTelegram, runner: AdminBotRunner
) -> None:
    event = in_review(client)
    runner.scan()
    review = only_message(fake, event["id"])
    fake.press(buttons(review)["✏️ Request changes"], message_id_of(fake, review))
    runner.poll_once(0)
    prompt_id = message_id_of(fake, fake.bodies("sendMessage")[-1])
    db.execute(
        "update app.bot_pending_replies set created_at = now() - interval '1 hour',"
        " expires_at = now() - interval '1 minute'"
    )
    fake.reply("Too late", prompt_id)
    runner.poll_once(0)
    assert get_event(client, event["id"])["status"] == "in_review"
    assert "expired" in fake.bodies("sendMessage")[-1]["text"]


def test_failed_guard_changes_nothing_and_says_why(
    client: TestClient, db: Conn, fake: FakeTelegram, runner: AdminBotRunner
) -> None:
    event = in_review(client, official_url="http://localhost/hackathon")
    runner.scan()
    review = only_message(fake, event["id"])
    fake.press(buttons(review)["✅ Approve"], message_id_of(fake, review))
    runner.poll_once(0)
    assert get_event(client, event["id"])["status"] == "in_review"
    assert (
        fake.answers()[-1] == "Not done: cannot approve: official_url must point to a public host"
    )
    assert [a["actor"] for a in actions(db, event["id"])] == ["admin_ui"]
    assert notifications(db, event["id"])[0]["resolution"] is None  # buttons stay usable


# --- stale, expired and foreign presses ----------------------------------------------


def test_press_after_a_decision_elsewhere_is_outdated(
    client: TestClient, db: Conn, fake: FakeTelegram, runner: AdminBotRunner
) -> None:
    event = in_review(client)
    runner.scan()
    review = only_message(fake, event["id"])
    client.post(f"/events/{event['id']}/transitions", json={"action": "approve"})

    fake.press(buttons(review)["⛔ Reject"], message_id_of(fake, review))
    runner.poll_once(0)
    assert get_event(client, event["id"])["status"] == "approved"
    assert fake.answers() == ["Outdated: this changed since the message was sent."]
    assert "Outdated: now <i>approved</i>." in fake.bodies("editMessageText")[-1]["text"]
    assert notifications(db, event["id"])[0]["resolution"] == "superseded"

    fake.press(buttons(review)["✅ Approve"], message_id_of(fake, review))  # pressed again
    runner.poll_once(0)
    assert fake.answers()[-1] == "Already handled (superseded)."


def test_scan_retires_messages_decided_in_the_admin_ui(
    client: TestClient, db: Conn, fake: FakeTelegram, runner: AdminBotRunner
) -> None:
    event = in_review(client)
    runner.scan()
    review = only_message(fake, event["id"])
    client.post(f"/events/{event['id']}/transitions", json={"action": "reject", "reason": "no"})
    runner.scan()
    edit = fake.bodies("editMessageText")[-1]
    assert edit["message_id"] == message_id_of(fake, review)
    assert "Now <i>rejected</i>; nothing to do here." in edit["text"]
    assert notifications(db, event["id"])[0]["resolution"] == "superseded"


def test_tampered_token_is_refused(
    client: TestClient, db: Conn, fake: FakeTelegram, runner: AdminBotRunner
) -> None:
    event = in_review(client)
    runner.scan()
    review = only_message(fake, event["id"])
    data = buttons(review)["✅ Approve"]
    fake.press(data[:-8] + "00000000", message_id_of(fake, review))
    runner.poll_once(0)
    assert get_event(client, event["id"])["status"] == "in_review"
    assert fake.answers() == ["Unknown button."]
    assert notifications(db, event["id"])[0]["resolution"] is None  # real buttons still work


def test_old_buttons_expire_and_a_fresh_message_follows(
    client: TestClient, db: Conn, fake: FakeTelegram, runner: AdminBotRunner
) -> None:
    event = in_review(client)
    runner.scan()
    review = only_message(fake, event["id"])
    db.execute(
        "update app.bot_notifications set sent_at = now() - interval '13 hours'"
        " where entity_id = %s",
        (event["id"],),
    )
    fake.press(buttons(review)["✅ Approve"], message_id_of(fake, review))
    runner.poll_once(0)
    assert get_event(client, event["id"])["status"] == "in_review"
    assert fake.answers() == ["These buttons expired. A fresh message follows if still needed."]
    assert "Buttons expired after 12 h." in fake.bodies("editMessageText")[-1]["text"]

    runner.scan()
    assert len(fake.sent_about(UUID(event["id"]).hex)) == 2
    assert [n["resolution"] for n in notifications(db, event["id"])] == ["expired", None]


def test_presses_from_strangers_and_groups_do_nothing(
    client: TestClient,
    db: Conn,
    fake: FakeTelegram,
    runner: AdminBotRunner,
    caplog: pytest.LogCaptureFixture,
) -> None:
    event = in_review(client)
    runner.scan()
    review = only_message(fake, event["id"])
    data = buttons(review)["✅ Approve"]
    fake.press(data, message_id_of(fake, review), user_id=STRANGER_ID)
    fake.press(data, message_id_of(fake, review), chat_id=-100123)  # admin, but in a group
    fake.reply("hello, my phone is +905551112233", 1, user_id=STRANGER_ID)
    fake.clear_calls()
    with caplog.at_level(logging.DEBUG):
        assert runner.poll_once(0) == 3

    assert get_event(client, event["id"])["status"] == "in_review"
    assert fake.answers() == ["Not allowed.", "Not available here."]
    assert fake.bodies("sendMessage") == []  # strangers get no reply
    assert [a["actor"] for a in actions(db, event["id"])] == ["admin_ui"]
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "not on the allowlist" in logged
    assert "+90555" not in logged and str(STRANGER_ID) not in logged
    assert ADMIN_LEAK_MARKER not in logged


def test_unknown_button_and_unknown_message(
    client: TestClient, fake: FakeTelegram, runner: AdminBotRunner
) -> None:
    fake.press("garbage", 4242)
    fake.press("v1:ap:e:" + "0" * 32 + ":0123abcd", 4242)
    runner.poll_once(0)
    assert fake.answers() == ["Unknown button.", "This message is not active any more."]


# --- applications --------------------------------------------------------------------


def test_application_notifications_carry_no_personal_details(
    client: TestClient, db: Conn, fake: FakeTelegram, runner: AdminBotRunner
) -> None:
    community = insert_community_application(
        db,
        full_name="Pytest M3 Zeynep Kaya",
        message="please call me",
        preferred_channel="whatsapp",
        telegram_username=None,
        phone="+905551112233",
    )
    team = insert_team_application(db, full_name="Pytest M3 Mehmet", skills="secret skills")
    runner.scan()

    text = only_message(fake, str(community["id"]))["text"]
    assert "Community application" in text and "Pytest" in text and "WhatsApp" in text
    for private in ("Zeynep", "Kaya", "+90555", "please call me"):
        assert private not in text
    team_text = only_message(fake, str(team["id"]))["text"]
    assert "Team application" in team_text and "secret skills" not in team_text


def test_application_status_from_telegram_is_audited(
    client: TestClient, db: Conn, fake: FakeTelegram, runner: AdminBotRunner
) -> None:
    application = insert_community_application(db)
    runner.scan()
    body = only_message(fake, str(application["id"]))
    assert list(buttons(body)) == ["Contacted", "Accepted", "Declined", "Spam"]
    fake.press(buttons(body)["Accepted"], message_id_of(fake, body))
    runner.poll_once(0)

    row = db.execute(
        "select status from app.community_applications where id = %s", (application["id"],)
    ).fetchone()
    assert row == {"status": "accepted"}
    assert actions(db, str(application["id"])) == [
        {
            "actor": "telegram:1111",
            "action": "set_status",
            "detail": {"from": "new", "to": "accepted"},
        }
    ]
    assert "Marked accepted by telegram:1111" in fake.bodies("editMessageText")[-1]["text"]
    runner.scan()
    assert len(fake.sent_about(application["id"].hex)) == 1  # no re-notification


# --- updates and offset --------------------------------------------------------------


def test_offset_is_persisted_and_updates_are_not_reprocessed(
    client: TestClient,
    db: Conn,
    fake: FakeTelegram,
    revalidator: RecordingRevalidator,
    runner: AdminBotRunner,
) -> None:
    update_id = fake.reply("/start", 1)
    assert runner.poll_once(0) == 1
    assert "FHC admin bot" in fake.bodies("sendMessage")[-1]["text"]
    row = db.execute(
        "select value from app.bot_state where key = 'admin_bot.987654321.update_offset'"
    ).fetchone()
    assert row == {"value": str(update_id + 1)}

    restarted = make_runner(db, fake, revalidator)
    assert restarted.poll_once(0) == 0  # offset loaded: the update is not handled twice
    assert fake.bodies("getUpdates")[-1]["offset"] == update_id + 1

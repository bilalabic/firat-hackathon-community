"""Admin bot channel offers (V1.1a + V1.1b): "Post to channel" after a publish and "Update
channel post" after an edit, with a two-step confirm, through the same publishing service
as the admin UI. Local DB (rolled back) and two fake bots (admin and channel)."""

from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from typing import Any
from uuid import UUID

import httpx2
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from fhc_api.admin_bot import outbox
from fhc_api.admin_bot.bot import AdminBot
from fhc_api.admin_bot.runner import AdminBotRunner
from fhc_api.admin_bot.settings import AdminBotConfig
from fhc_api.db import Conn
from fhc_api.publishing.service import ChannelPublisher
from tests.conftest import RecordingRevalidator, make_settings
from tests.factories import create_event
from tests.fake_telegram import (
    ADMIN_ID,
    ADMIN_TOKEN,
    CHANNEL_TOKEN,
    CHANNEL_USERNAME,
    FakeTelegram,
    buttons,
    fail,
)

CHANNEL_SETTINGS = {
    "TELEGRAM_BOT_TOKEN": CHANNEL_TOKEN,
    "TELEGRAM_CHANNEL_ID": CHANNEL_USERNAME,
    "WEB_BASE_URL": "https://fhc.example.org",
}


@pytest.fixture(autouse=True)
def _setup(monkeypatch: pytest.MonkeyPatch, db: Conn) -> None:
    monkeypatch.setattr(outbox, "SEND_PACING_S", 0.0)
    # Events published earlier (e.g. the local seed) must not be offered in these tests.
    db.execute(
        "update app.events set published_at = now() - interval '3 days' where status = 'published'"
    )


@pytest.fixture
def admin_fake() -> FakeTelegram:
    return FakeTelegram()


@pytest.fixture
def channel_fake() -> FakeTelegram:
    return FakeTelegram()


@pytest.fixture
def publisher(channel_fake: FakeTelegram) -> ChannelPublisher:
    return ChannelPublisher(make_settings(**CHANNEL_SETTINGS), channel_fake.channel_client())


def make_runner(
    db: Conn, admin_fake: FakeTelegram, channel: ChannelPublisher | None
) -> AdminBotRunner:
    @contextmanager
    def open_conn() -> Iterator[Conn]:
        with db.transaction():
            yield db

    config = AdminBotConfig(token=SecretStr(ADMIN_TOKEN), admin_ids=frozenset({ADMIN_ID}))
    return AdminBotRunner(
        config, admin_fake.client(), open_conn, RecordingRevalidator(), channel=channel
    )


@pytest.fixture
def runner(db: Conn, admin_fake: FakeTelegram, publisher: ChannelPublisher) -> AdminBotRunner:
    return make_runner(db, admin_fake, publisher)


def publish(client: TestClient, **overrides: Any) -> dict[str, Any]:
    event = create_event(client, **overrides)
    for action in ("submit", "approve", "publish"):
        response = client.post(f"/events/{event['id']}/transitions", json={"action": action})
        assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def offers(fake: FakeTelegram, event_id: str) -> list[dict[str, Any]]:
    return fake.sent_about(UUID(event_id).hex)


def message_id_of(fake: FakeTelegram, body: dict[str, Any]) -> int:
    return 100 + fake.bodies("sendMessage").index(body)


def notes(db: Conn, event_id: str) -> list[tuple[str, str | None]]:
    rows = db.execute(
        "select kind, resolution from app.bot_notifications where entity_id = %s",
        (event_id,),
    ).fetchall()
    return sorted((row["kind"], row["resolution"]) for row in rows)


def channel_rows(db: Conn, event_id: str) -> list[dict[str, Any]]:
    return db.execute(
        "select status, content_version from app.publications where event_id = %s",
        (event_id,),
    ).fetchall()


def confirm(
    admin_fake: FakeTelegram, runner: AdminBotRunner, offer: dict[str, Any], first: str, second: str
) -> None:
    offer_id = message_id_of(admin_fake, offer)
    admin_fake.press(buttons(offer)[first], offer_id)
    runner.poll_once(0)
    step = admin_fake.bodies("editMessageReplyMarkup")[-1]
    assert step["message_id"] == offer_id
    assert list(buttons(step)) == [second, "Cancel"]
    admin_fake.press(buttons(step)[second], offer_id)
    runner.poll_once(0)


def test_post_to_channel_after_publish(
    client: TestClient,
    db: Conn,
    admin_fake: FakeTelegram,
    channel_fake: FakeTelegram,
    runner: AdminBotRunner,
) -> None:
    event = publish(client, title="Pytest M3 Bot Kanal")
    runner.scan()
    runner.scan()  # once per state
    [offer] = offers(admin_fake, event["id"])
    assert "Published, not in the channel yet" in offer["text"]
    assert list(buttons(offer)) == ["📣 Post to channel", "Later"]

    # The first press only asks for confirmation; nothing is posted.
    offer_id = message_id_of(admin_fake, offer)
    admin_fake.press(buttons(offer)["📣 Post to channel"], offer_id)
    runner.poll_once(0)
    assert channel_fake.calls == []
    assert admin_fake.answers()[-1] == "Confirm to post to the public channel."

    step = admin_fake.bodies("editMessageReplyMarkup")[-1]
    admin_fake.press(buttons(step)["📣 Confirm post"], offer_id)
    runner.poll_once(0)
    [photo] = channel_fake.bodies("sendPhoto")
    assert photo["chat_id"] == CHANNEL_USERNAME
    assert "<b>Pytest M3 Bot Kanal</b>" in photo["caption"]
    assert admin_fake.answers()[-1] == "Working on it…"
    outcome = admin_fake.bodies("editMessageText")[-1]
    assert outcome["message_id"] == offer_id
    assert "📣 Posted to the channel by telegram:1111" in outcome["text"]
    assert channel_rows(db, event["id"]) == [{"status": "sent", "content_version": 1}]
    assert notes(db, event["id"]) == [("channel_post", "posted")]
    row = db.execute(
        "select actor, detail from app.admin_actions where entity_id = %s"
        " and action = 'telegram_post'",
        (event["id"],),
    ).fetchone()
    assert row is not None
    assert row["actor"] == "telegram:1111"
    assert row["detail"]["outcome"] == "sent"

    # Posted: no further offer, even after more scans.
    admin_fake.clear_calls()
    runner.scan()
    assert offers(admin_fake, event["id"]) == []


def test_update_offer_after_an_edit(
    client: TestClient,
    db: Conn,
    admin_fake: FakeTelegram,
    channel_fake: FakeTelegram,
    runner: AdminBotRunner,
    publisher: ChannelPublisher,
) -> None:
    event = publish(client)
    runner.scan()
    [offer] = offers(admin_fake, event["id"])
    confirm(admin_fake, runner, offer, "📣 Post to channel", "📣 Confirm post")
    assert len(channel_fake.bodies("sendPhoto")) == 1

    response = client.patch(f"/events/{event['id']}", json={"city": "Malatya"})
    assert response.status_code == 200
    runner.scan()
    [_, update_offer] = offers(admin_fake, event["id"])
    assert "Changed since the channel post" in update_offer["text"]
    assert list(buttons(update_offer)) == ["🔄 Update channel post", "Later"]

    confirm(admin_fake, runner, update_offer, "🔄 Update channel post", "🔄 Confirm update")
    assert len(channel_fake.bodies("editMessageMedia")) == 1  # the card changed
    assert channel_rows(db, event["id"]) == [{"status": "edited", "content_version": 2}]
    assert "🔄 Channel post updated" in admin_fake.bodies("editMessageText")[-1]["text"]


def test_offer_is_retired_when_posted_from_the_admin_ui(
    client: TestClient,
    db: Conn,
    admin_fake: FakeTelegram,
    channel_fake: FakeTelegram,
    runner: AdminBotRunner,
    publisher: ChannelPublisher,
) -> None:
    event = publish(client)
    runner.scan()
    [offer] = offers(admin_fake, event["id"])

    @contextmanager
    def open_conn() -> Iterator[Conn]:
        with db.transaction():
            yield db

    publisher.send(open_conn, UUID(event["id"]), actor="admin_ui", expected_hash=None)
    runner.scan()
    retired = admin_fake.bodies("editMessageText")[-1]
    assert retired["message_id"] == message_id_of(admin_fake, offer)
    assert "channel post changed" in retired["text"]
    assert ("channel_post", "superseded") in notes(db, event["id"])

    # A press on the old offer is refused; nothing is posted twice.
    admin_fake.press(buttons(offer)["📣 Post to channel"], message_id_of(admin_fake, offer))
    runner.poll_once(0)
    assert len(channel_fake.bodies("sendPhoto")) == 1


def test_failed_post_keeps_the_offer_and_reports_why(
    client: TestClient,
    db: Conn,
    admin_fake: FakeTelegram,
    channel_fake: FakeTelegram,
    runner: AdminBotRunner,
) -> None:
    event = publish(client)
    runner.scan()
    [offer] = offers(admin_fake, event["id"])
    channel_fake.failures["sendPhoto"] = fail(403, "Forbidden: bot is not a member")
    confirm(admin_fake, runner, offer, "📣 Post to channel", "📣 Confirm post")
    report = admin_fake.bodies("sendMessage")[-1]
    assert report["chat_id"] == ADMIN_ID
    assert report["text"].startswith("Channel: not done.")
    assert "not an administrator" in report["text"]
    assert channel_rows(db, event["id"]) == [{"status": "failed", "content_version": 1}]
    assert notes(db, event["id"])[0] == ("channel_post", None)  # still offered

    # Retry from the same message works once Telegram accepts.
    del channel_fake.failures["sendPhoto"]
    confirm(admin_fake, runner, offer, "📣 Post to channel", "📣 Confirm post")
    assert sorted(row["status"] for row in channel_rows(db, event["id"])) == ["failed", "sent"]
    assert len(channel_fake.channel_posts) == 1
    assert ("channel_post", "posted") in notes(db, event["id"])


def test_uncertain_post_is_not_offered_again(
    client: TestClient,
    db: Conn,
    admin_fake: FakeTelegram,
    channel_fake: FakeTelegram,
    runner: AdminBotRunner,
    publisher: ChannelPublisher,
) -> None:
    event = publish(client)
    runner.scan()
    [offer] = offers(admin_fake, event["id"])

    def timeout(body: dict[str, Any]) -> None:
        raise httpx2.ReadTimeout("timed out")

    channel_fake.hooks["sendPhoto"] = timeout
    confirm(admin_fake, runner, offer, "📣 Post to channel", "📣 Confirm post")
    report = admin_fake.bodies("sendMessage")[-1]
    assert "may have been published" in report["text"]
    row = db.execute(
        "select status, uncertain from app.publications where event_id = %s", (event["id"],)
    ).fetchone()
    assert row == {"status": "failed", "uncertain": True}

    # The API and the bot agree: no "Post to channel" while the message may exist.
    channel_fake.hooks.clear()
    state = publisher.preview(db, UUID(event["id"]))
    assert (state.post_state, state.can_send) == ("uncertain", False)
    runner.scan()
    runner.scan()
    assert ("channel_post", "superseded") in notes(db, event["id"])
    assert len(offers(admin_fake, event["id"])) == 1  # the first one, retired
    admin_fake.press(buttons(offer)["📣 Post to channel"], message_id_of(admin_fake, offer))
    runner.poll_once(0)
    assert len(channel_fake.bodies("sendPhoto")) == 1


def test_interrupted_send_is_not_offered(
    client: TestClient,
    db: Conn,
    admin_fake: FakeTelegram,
    runner: AdminBotRunner,
    publisher: ChannelPublisher,
) -> None:
    """A draft left by a crash: the API reports it uncertain and the bot does not offer
    "Post to channel" (both read the same post)."""
    event = publish(client)
    db.execute(
        "insert into app.publications"
        " (event_id, platform, target, content_hash, body, status, created_at)"
        " values (%s, 'telegram', '@x', repeat('a', 64), 'b', 'draft',"
        " now() - interval '11 minutes')",
        (event["id"],),
    )
    state = publisher.preview(db, UUID(event["id"]))
    assert (state.post_state, state.can_send) == ("uncertain", False)
    runner.scan()
    assert offers(admin_fake, event["id"]) == []


def test_later_resolves_the_offer(
    client: TestClient, db: Conn, admin_fake: FakeTelegram, runner: AdminBotRunner
) -> None:
    event = publish(client)
    runner.scan()
    [offer] = offers(admin_fake, event["id"])
    admin_fake.press(buttons(offer)["Later"], message_id_of(admin_fake, offer))
    runner.poll_once(0)
    assert "Publishing → Telegram" in admin_fake.bodies("editMessageText")[-1]["text"]
    assert ("channel_post", "later") in notes(db, event["id"])
    runner.scan()
    assert len(offers(admin_fake, event["id"])) == 1  # not offered again for this state


def test_no_offers_without_channel_publishing_or_for_old_events(
    client: TestClient, db: Conn, admin_fake: FakeTelegram
) -> None:
    event = publish(client)
    make_runner(db, admin_fake, None).scan()
    assert offers(admin_fake, event["id"]) == []

    db.execute(
        "update app.events set published_at = now() - interval '13 hours' where id = %s",
        (event["id"],),
    )
    channel = ChannelPublisher(make_settings(**CHANNEL_SETTINGS), FakeTelegram().channel_client())
    make_runner(db, admin_fake, channel).scan()
    assert offers(admin_fake, event["id"]) == []


@pytest.mark.parametrize("configured", [True, False])
def test_the_bot_gets_channel_publishing_only_when_configured(db: Conn, configured: bool) -> None:
    settings = make_settings(
        TELEGRAM_ADMIN_ENABLED="true",
        TELEGRAM_ADMIN_BOT_TOKEN=ADMIN_TOKEN,
        TELEGRAM_ADMIN_USER_IDS=str(ADMIN_ID),
        **(CHANNEL_SETTINGS if configured else {"TELEGRAM_BOT_TOKEN": None}),
    )
    channel = ChannelPublisher(settings, FakeTelegram().channel_client() if configured else None)
    bot = AdminBot(
        settings,
        lambda: nullcontext(db),
        RecordingRevalidator(),
        client=FakeTelegram().client(),
        channel=channel,
    )
    assert bot.runner is not None
    assert (bot.runner._handlers._ctx.channel is channel) is configured

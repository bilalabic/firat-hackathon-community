"""Telegram channel publishing (V1.1a) through the API, against the local database (rolled
back) and the fake Bot API. Never calls Telegram.

Inside one test transaction `now()` is constant; publishable-hash changes come from field
edits, which is what the hash looks at.
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import httpx2
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from fhc_api.db import Conn, ConnFactory, get_conn, get_conn_factory
from fhc_api.main import create_app
from fhc_api.publishing.hashing import card_hash
from fhc_api.publishing.service import ChannelPublisher
from tests.conftest import AUTH, BASE_URL, FakeUrlChecker, RecordingRevalidator, make_settings
from tests.factories import create_event, force_status
from tests.fake_telegram import (
    CHANNEL_CHAT_ID,
    CHANNEL_LEAK_MARKER,
    CHANNEL_TOKEN,
    CHANNEL_USERNAME,
    FakeTelegram,
    fail,
)

WEB = "https://fhc.example.org"
CHANNEL_ENV = {
    "TELEGRAM_BOT_TOKEN": CHANNEL_TOKEN,
    "TELEGRAM_CHANNEL_ID": CHANNEL_USERNAME,
    "WEB_BASE_URL": WEB,
}
PHOTO_URL_ERROR = "Bad Request: wrong file identifier/HTTP URL specified"


def make_client(app: FastAPI, db: Conn) -> TestClient:
    def conn_in_savepoint() -> Iterator[Conn]:
        with db.transaction():
            yield db

    app.dependency_overrides[get_conn] = conn_in_savepoint
    app.dependency_overrides[get_conn_factory] = lambda: contextmanager(conn_in_savepoint)
    return TestClient(app, base_url=BASE_URL, headers=AUTH)


@pytest.fixture
def fake() -> FakeTelegram:
    return FakeTelegram()


@pytest.fixture
def api(db: Conn, fake: FakeTelegram, revalidator: RecordingRevalidator) -> TestClient:
    app = create_app(
        make_settings(**CHANNEL_ENV),
        revalidator=revalidator,
        url_checker=FakeUrlChecker(),
        telegram_client=fake.channel_client(),
    )
    return make_client(app, db)


def published(api: TestClient, **overrides: Any) -> dict[str, Any]:
    """An event published through the state machine."""
    event = create_event(api, **overrides)
    for action in ("submit", "approve", "publish"):
        response = api.post(f"/events/{event['id']}/transitions", json={"action": action})
        assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def preview(api: TestClient, event_id: str) -> dict[str, Any]:
    response = api.get(f"/telegram/channel/events/{event_id}/preview")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def send(api: TestClient, event_id: str, content_hash: str | None = None) -> Any:
    content_hash = content_hash or preview(api, event_id)["content_hash"]
    return api.post(
        f"/telegram/channel/events/{event_id}/send", json={"content_hash": content_hash}
    )


def update(api: TestClient, event_id: str) -> Any:
    content_hash = preview(api, event_id)["content_hash"]
    return api.post(
        f"/telegram/channel/events/{event_id}/update", json={"content_hash": content_hash}
    )


def delete(api: TestClient, event_id: str, publication_id: str) -> Any:
    return api.post(
        f"/telegram/channel/events/{event_id}/delete", json={"publication_id": publication_id}
    )


def audit(db: Conn, event_id: str) -> list[tuple[str, str, str]]:
    """Sorted: `at` is constant inside the test transaction."""
    rows = db.execute(
        "select actor, action, detail from app.admin_actions"
        " where entity_id = %s and action like 'telegram%%'",
        (event_id,),
    ).fetchall()
    return sorted((row["actor"], row["action"], row["detail"]["outcome"]) for row in rows)


def publications(db: Conn, event_id: str) -> list[dict[str, Any]]:
    return db.execute(
        "select status, uncertain, content_version, message_type, external_id, target,"
        " image_url, error"
        " from app.publications where event_id = %s order by created_at, id",
        (event_id,),
    ).fetchall()


def insert_draft(db: Conn, event_id: str) -> str:
    row = db.execute(
        "insert into app.publications (event_id, platform, target, content_hash, body, status)"
        " values (%s, 'telegram', '@x', repeat('a', 64), 'b', 'draft') returning id",
        (event_id,),
    ).fetchone()
    assert row is not None
    return str(row["id"])


def age_drafts(db: Conn, event_id: str) -> None:
    """Older than STALE_DRAFT_MINUTES: left by a crash."""
    db.execute(
        "update app.publications set created_at = now() - interval '11 minutes'"
        " where event_id = %s and status = 'draft'",
        (event_id,),
    )


# --- end to end ------------------------------------------------------------------------


def test_publish_preview_send_edit_update_unpublish_delete(
    api: TestClient, db: Conn, fake: FakeTelegram
) -> None:
    event = published(api, title="Pytest M3 Kanal <Hack> & Co", city="Elazığ")
    event_id, slug = event["id"], event["slug"]

    # Preview: not posted yet, exact caption and versioned card URL.
    first = preview(api, event_id)
    assert first["configured"] is True
    assert first["post_state"] == "not_posted"
    assert (first["can_send"], first["can_update"], first["can_delete"]) == (True, False, False)
    assert first["detail_url"] == f"{WEB}/hackathonlar/{slug}"
    assert first["image_url"] == (
        f"{WEB}/hackathonlar/{slug}/opengraph-image?v={card_hash(event)[:16]}"
    )
    assert "<b>Pytest M3 Kanal &lt;Hack&gt; &amp; Co</b>" in first["caption_html"]
    assert "Pytest M3 Kanal <Hack> & Co" in first["caption_text"]
    assert first["caption_length"] <= 1024

    # Send: one sendPhoto to the channel; a sent row and an audit entry.
    response = send(api, event_id, first["content_hash"])
    assert response.status_code == 200, response.text
    sent = response.json()
    assert sent["outcome"] == "sent"
    [photo] = fake.bodies("sendPhoto")
    assert photo == {
        "chat_id": CHANNEL_USERNAME,
        "photo": first["image_url"],
        "caption": first["caption_html"],
        "parse_mode": "HTML",
    }
    publication = sent["publication"]
    assert publication["status"] == "sent"
    assert publication["target"] == str(CHANNEL_CHAT_ID)
    assert publication["content_version"] == 1
    assert publication["message_type"] == "photo"
    assert publication["content_hash"] == first["content_hash"]
    assert publication["body"] == first["caption_html"]
    assert publication["image_url"] == first["image_url"]
    assert publication["sent_at"] is not None
    assert preview(api, event_id)["post_state"] == "posted"
    assert send(api, event_id).status_code == 409  # no duplicate post

    # Edit a card field: changed since posted, and the card changed.
    assert api.patch(f"/events/{event_id}", json={"city": "Malatya"}).status_code == 200
    changed = preview(api, event_id)
    assert changed["post_state"] == "changed"
    assert changed["card_changed"] is True
    assert changed["can_update"] is True
    assert changed["image_url"] != first["image_url"]

    response = update(api, event_id)
    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "edited"
    [media] = fake.bodies("editMessageMedia")
    assert media["chat_id"] == CHANNEL_CHAT_ID
    assert media["message_id"] == int(publication["external_id"])
    assert media["media"] == {
        "type": "photo",
        "media": changed["image_url"],
        "caption": changed["caption_html"],
        "parse_mode": "HTML",
    }
    edited = response.json()["publication"]
    assert (edited["status"], edited["content_version"]) == ("edited", 2)
    assert edited["image_url"] == changed["image_url"]
    assert preview(api, event_id)["post_state"] == "posted"

    # A caption-only edit keeps the card: editMessageCaption, version 3.
    assert api.patch(f"/events/{event_id}", json={"summary": "Yeni özet."}).status_code == 200
    assert preview(api, event_id)["card_changed"] is False
    response = update(api, event_id)
    assert response.status_code == 200, response.text
    assert response.json()["publication"]["content_version"] == 3
    assert len(fake.bodies("editMessageCaption")) == 1
    assert len(fake.bodies("editMessageMedia")) == 1
    # Nothing changed: no Bot API call, no new version.
    again = update(api, event_id).json()
    assert again["outcome"] == "unchanged"
    assert again["publication"]["content_version"] == 3

    # Unpublish: the post is NOT deleted automatically; the preview says so.
    response = api.post(f"/events/{event_id}/transitions", json={"action": "unpublish"})
    assert response.status_code == 200
    assert fake.bodies("deleteMessage") == []
    hidden = preview(api, event_id)
    assert hidden["post_state"] == "not_public"
    assert (hidden["can_send"], hidden["can_update"], hidden["can_delete"]) == (False, False, True)
    assert update(api, event_id).status_code == 409
    listed = api.get("/telegram/channel/posts").json()["items"]
    assert listed[0]["event_id"] == event_id  # not-public posts come first
    assert listed[0]["post_state"] == "not_public"

    # Delete.
    response = delete(api, event_id, hidden["current_post"]["id"])
    assert response.status_code == 200, response.text
    assert response.json()["outcome"] == "deleted"
    assert fake.bodies("deleteMessage") == [
        {"chat_id": CHANNEL_CHAT_ID, "message_id": int(publication["external_id"])}
    ]
    assert fake.channel_posts == {}
    after = preview(api, event_id)
    assert after["post_state"] == "not_posted"
    assert after["can_send"] is False  # not published

    history = api.get(f"/telegram/channel/events/{event_id}/history").json()
    assert [post["status"] for post in history["posts"]] == ["deleted"]
    assert audit(db, event_id) == [
        ("admin_ui", "telegram_delete", "deleted"),
        ("admin_ui", "telegram_post", "sent"),
        ("admin_ui", "telegram_update", "edited"),
        ("admin_ui", "telegram_update", "edited"),
        ("admin_ui", "telegram_update", "unchanged"),
    ]
    assert len(history["actions"]) == 5

    # Published again: a new post is allowed after the deleted one.
    api.post(f"/events/{event_id}/transitions", json={"action": "publish"})
    assert send(api, event_id).status_code == 200
    assert sorted(row["status"] for row in publications(db, event_id)) == ["deleted", "sent"]


# --- rules -----------------------------------------------------------------------------


def test_only_published_events_are_sent(api: TestClient, fake: FakeTelegram) -> None:
    event = create_event(api)
    state = preview(api, event["id"])
    assert state["can_send"] is False
    response = send(api, event["id"], state["content_hash"])
    assert response.status_code == 409
    assert "only published events" in response.json()["detail"]
    assert fake.calls == []


def test_send_refuses_a_stale_preview(api: TestClient, fake: FakeTelegram) -> None:
    event = published(api)
    old_hash = preview(api, event["id"])["content_hash"]
    api.patch(f"/events/{event['id']}", json={"title": "Pytest M3 Renamed"})
    response = send(api, event["id"], old_hash)
    assert response.status_code == 409
    assert "changed since the preview" in response.json()["detail"]
    assert fake.calls == []


def test_a_fresh_draft_blocks_and_a_stale_one_is_uncertain(
    api: TestClient, db: Conn, fake: FakeTelegram
) -> None:
    event = published(api)
    insert_draft(db, event["id"])
    assert preview(api, event["id"])["post_state"] == "sending"
    response = send(api, event["id"])
    assert response.status_code == 409
    assert "being sent" in response.json()["detail"]

    # Left by a crash: the message may exist, so it is not sent again.
    age_drafts(db, event["id"])
    state = preview(api, event["id"])
    assert state["post_state"] == "uncertain"
    assert (state["can_send"], state["can_resolve"]) == (False, True)
    response = send(api, event["id"])
    assert response.status_code == 409
    assert "may have reached the channel" in response.json()["detail"]
    assert fake.calls == []
    [row] = publications(db, event["id"])
    assert (row["status"], row["uncertain"]) == ("failed", True)
    assert "interrupted" in row["error"]
    assert audit(db, event["id"]) == [("admin_ui", "telegram_post", "interrupted")]
    assert preview(api, event["id"])["post_state"] == "uncertain"
    assert send(api, event["id"]).status_code == 409


def _timeout(body: dict[str, Any]) -> None:
    raise httpx2.ReadTimeout("timed out")


@pytest.mark.parametrize("failure", ["timeout", "non_json", "unexpected_result", "server_error"])
def test_ambiguous_send_failures_are_uncertain(
    api: TestClient, db: Conn, fake: FakeTelegram, failure: str
) -> None:
    event = published(api)
    if failure == "timeout":
        fake.hooks["sendPhoto"] = _timeout
    elif failure == "non_json":
        fake.failures["sendPhoto"] = httpx2.Response(502, text="Bad Gateway")
    elif failure == "unexpected_result":
        fake.failures["sendPhoto"] = httpx2.Response(200, json={"ok": True, "result": {"x": 1}})
    else:
        fake.failures["sendPhoto"] = fail(500, "Internal Server Error")
    result = send(api, event["id"])
    assert result.status_code == 502
    assert "may have been published" in result.json()["detail"]
    assert fake.bodies("sendMessage") == []  # no text fallback either
    [row] = publications(db, event["id"])
    assert (row["status"], row["uncertain"]) == ("failed", True)
    assert audit(db, event["id"]) == [("admin_ui", "telegram_post", "uncertain")]

    state = preview(api, event["id"])
    assert state["post_state"] == "uncertain"
    assert (state["can_send"], state["can_update"], state["can_delete"]) == (False, False, False)
    assert state["can_resolve"] is True
    assert state["current_post"]["uncertain"] is True
    listed = api.get("/telegram/channel/posts", params={"limit": 200}).json()["items"]
    assert {item["event_id"]: item["post_state"] for item in listed}[event["id"]] == "uncertain"

    # Telegram answers again: still no second post until the operator resolves it.
    fake.hooks.clear()
    fake.failures.clear()
    response = send(api, event["id"])
    assert response.status_code == 409
    assert "resolve the post" in response.json()["detail"]
    assert len(fake.bodies("sendPhoto")) == 1


def resolve(api: TestClient, event_id: str, publication_id: str, **body: Any) -> Any:
    return api.post(
        f"/telegram/channel/events/{event_id}/posts/{publication_id}/resolve",
        json={"outcome": "not_in_channel", **body},
    )


def test_resolve_an_uncertain_post(api: TestClient, db: Conn, fake: FakeTelegram) -> None:
    event = published(api)
    fake.hooks["sendPhoto"] = _timeout
    assert send(api, event["id"]).status_code == 502
    fake.hooks.clear()
    post = preview(api, event["id"])["current_post"]

    other = published(api, title="Pytest M3 Other")
    assert resolve(api, other["id"], post["id"]).status_code == 404
    assert resolve(api, event["id"], "00000000-0000-4000-8000-000000000000").status_code == 404
    assert resolve(api, event["id"], post["id"], outcome="in_channel").status_code == 422

    response = resolve(api, event["id"], post["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "not_in_channel"
    resolved = body["publication"]
    assert (resolved["status"], resolved["uncertain"]) == ("failed", False)
    assert "may have been published" in resolved["error"]
    assert resolved["error"].endswith("Checked by the operator: not in the channel.")
    state = preview(api, event["id"])
    assert state["post_state"] == "not_posted"
    assert (state["can_send"], state["can_resolve"]) == (True, False)
    assert fake.bodies("deleteMessage") == []  # no Bot API call

    # Only an uncertain post can be resolved.
    assert resolve(api, event["id"], post["id"]).status_code == 409
    sent = send(api, event["id"])
    assert sent.status_code == 200
    response = resolve(api, event["id"], sent.json()["publication"]["id"])
    assert response.status_code == 409
    assert "status sent" in response.json()["detail"]

    assert audit(db, event["id"]) == [
        ("admin_ui", "telegram_post", "sent"),
        ("admin_ui", "telegram_post", "uncertain"),
        ("admin_ui", "telegram_resolve", "not_in_channel"),
    ]
    actions = api.get(f"/telegram/channel/events/{event['id']}/history").json()["actions"]
    assert "telegram_resolve" in [action["action"] for action in actions]


def test_resolve_an_interrupted_send(api: TestClient, db: Conn, fake: FakeTelegram) -> None:
    event = published(api)
    draft = insert_draft(db, event["id"])
    response = resolve(api, event["id"], draft)
    assert response.status_code == 409  # a fresh draft: the send may still be running
    assert "status draft" in response.json()["detail"]

    age_drafts(db, event["id"])
    response = resolve(api, event["id"], draft)
    assert response.status_code == 200, response.text
    assert response.json()["publication"]["uncertain"] is False
    assert audit(db, event["id"]) == [
        ("admin_ui", "telegram_post", "interrupted"),
        ("admin_ui", "telegram_resolve", "not_in_channel"),
    ]
    assert send(api, event["id"]).status_code == 200
    assert len(fake.bodies("sendPhoto")) == 1


def test_card_fetch_failure_falls_back_to_a_text_post(
    api: TestClient, db: Conn, fake: FakeTelegram
) -> None:
    event = published(api)
    fake.failures["sendPhoto"] = fail(400, PHOTO_URL_ERROR)
    response = send(api, event["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "sent_as_text"
    [text] = fake.bodies("sendMessage")
    assert text["link_preview_options"] == {
        "url": f"{WEB}/hackathonlar/{event['slug']}",
        "prefer_large_media": True,
        "show_above_text": True,
    }
    assert text["parse_mode"] == "HTML"
    row = publications(db, event["id"])[0]
    assert (row["status"], row["message_type"], row["image_url"]) == ("sent", "text", None)
    assert "could not use the event card" in row["error"]
    assert audit(db, event["id"]) == [("admin_ui", "telegram_post", "sent_as_text")]

    # The card works again: the next update turns the text post into a photo post.
    del fake.failures["sendPhoto"]
    api.patch(f"/events/{event['id']}", json={"summary": "Güncel özet."})
    response = update(api, event["id"])
    assert response.status_code == 200, response.text
    assert response.json()["publication"]["message_type"] == "photo"
    assert len(fake.bodies("editMessageMedia")) == 1


def test_text_post_stays_text_when_the_card_still_fails(
    api: TestClient, fake: FakeTelegram
) -> None:
    event = published(api)
    fake.failures["sendPhoto"] = fail(400, PHOTO_URL_ERROR)
    fake.failures["editMessageMedia"] = fail(400, "Bad Request: failed to get HTTP URL content")
    send(api, event["id"])
    api.patch(f"/events/{event['id']}", json={"summary": "Güncel özet."})
    body = update(api, event["id"]).json()
    assert body["outcome"] == "edited"
    assert body["publication"]["message_type"] == "text"
    assert len(fake.bodies("editMessageText")) == 1


def test_card_change_with_unavailable_card_updates_only_the_caption(
    api: TestClient, fake: FakeTelegram
) -> None:
    event = published(api)
    send(api, event["id"])
    fake.failures["editMessageMedia"] = fail(400, "Bad Request: IMAGE_PROCESS_FAILED")
    api.patch(f"/events/{event['id']}", json={"city": "Van"})
    body = update(api, event["id"]).json()
    assert body["outcome"] == "edited_caption_only"
    assert len(fake.bodies("editMessageCaption")) == 1
    # The old card URL stays recorded, so the preview still offers to replace the card.
    assert preview(api, event["id"])["card_changed"] is True


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (fail(403, "Forbidden: bot is not a member of the channel chat"), "not an administrator"),
        (fail(400, "Bad Request: chat not found"), "TELEGRAM_CHANNEL_ID"),
        (fail(401, "Unauthorized"), "TELEGRAM_BOT_TOKEN"),
        (
            httpx2.Response(
                429,
                json={
                    "ok": False,
                    "error_code": 429,
                    "description": "Too Many Requests: retry after 7",
                    "parameters": {"retry_after": 7},
                },
            ),
            "retry after 7 s",
        ),
    ],
)
def test_telegram_errors_are_recorded_and_mapped(
    api: TestClient, db: Conn, fake: FakeTelegram, response: httpx2.Response, expected: str
) -> None:
    event = published(api)
    fake.failures["sendPhoto"] = response
    result = send(api, event["id"])
    assert result.status_code == 502
    assert expected in result.json()["detail"]
    assert fake.bodies("sendMessage") == []  # no text fallback for these
    [row] = publications(db, event["id"])
    assert row["status"] == "failed"
    assert expected in row["error"]
    assert audit(db, event["id"]) == [("admin_ui", "telegram_post", "failed")]
    # A failed attempt does not block a retry.
    del fake.failures["sendPhoto"]
    assert send(api, event["id"]).status_code == 200


def test_update_of_a_post_deleted_in_the_channel(
    api: TestClient, db: Conn, fake: FakeTelegram
) -> None:
    event = published(api)
    send(api, event["id"])
    fake.channel_posts.clear()  # deleted by hand in Telegram
    api.patch(f"/events/{event['id']}", json={"summary": "Güncel özet."})
    response = update(api, event["id"])
    assert response.status_code == 409
    assert "no longer exists" in response.json()["detail"]
    assert publications(db, event["id"])[0]["status"] == "deleted"
    assert preview(api, event["id"])["can_send"] is True


def test_delete_refused_by_telegram_then_deleted_by_hand(
    api: TestClient, db: Conn, fake: FakeTelegram
) -> None:
    event = published(api)
    post = send(api, event["id"]).json()["publication"]
    fake.failures["deleteMessage"] = fail(400, "Bad Request: message can't be deleted")
    response = delete(api, event["id"], post["id"])
    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "48 hours" in detail and "T-1" in detail
    row = publications(db, event["id"])[0]
    assert row["status"] == "sent"  # still live
    assert "48 hours" in row["error"]

    # The owner deletes it in the channel; Delete again marks it deleted.
    del fake.failures["deleteMessage"]
    fake.channel_posts.clear()
    response = delete(api, event["id"], post["id"])
    assert response.status_code == 200
    assert response.json()["outcome"] == "already_gone"
    assert publications(db, event["id"])[0]["status"] == "deleted"
    assert audit(db, event["id"]) == [
        ("admin_ui", "telegram_delete", "already_gone"),
        ("admin_ui", "telegram_delete", "failed"),
        ("admin_ui", "telegram_post", "sent"),
    ]
    assert delete(api, event["id"], post["id"]).status_code == 409  # already deleted


def test_delete_checks_the_event(api: TestClient, fake: FakeTelegram) -> None:
    event = published(api)
    other = published(api, title="Pytest M3 Other")
    post = send(api, event["id"]).json()["publication"]
    assert delete(api, other["id"], post["id"]).status_code == 404
    assert fake.bodies("deleteMessage") == []


def test_unknown_event_is_404(api: TestClient) -> None:
    missing = "00000000-0000-4000-8000-000000000000"
    assert api.get(f"/telegram/channel/events/{missing}/preview").status_code == 404
    assert api.get(f"/telegram/channel/events/{missing}/history").status_code == 404
    assert send(api, missing, "a" * 64).status_code == 404


def test_long_event_caption_fits(api: TestClient, db: Conn) -> None:
    event = published(
        api,
        title="Pytest M3 " + "Uzun Başlık " * 12,
        organizer="O" * 160,
        summary=("Çok uzun bir özet metni. " * 20)[:300],
        venue="V" * 200,
        city="C" * 120,
        country="JP",
    )
    state = preview(api, event["id"])
    assert state["caption_length"] <= 1024
    assert state["caption_truncated"] is True
    assert send(api, event["id"], state["content_hash"]).status_code == 200


def test_token_never_appears_in_responses_or_logs(
    api: TestClient, fake: FakeTelegram, caplog: pytest.LogCaptureFixture
) -> None:
    event = published(api)
    with caplog.at_level(logging.DEBUG):
        texts = [send(api, event["id"]).text]
        fake.failures["editMessageCaption"] = fail(403, "Forbidden: not enough rights")
        api.patch(f"/events/{event['id']}", json={"summary": "x" * 20})
        texts.append(update(api, event["id"]).text)
        texts.append(api.get(f"/telegram/channel/events/{event['id']}/history").text)
        texts.append(api.get("/telegram/channel/posts").text)
    for text in texts:
        assert CHANNEL_LEAK_MARKER not in text
    assert all(CHANNEL_LEAK_MARKER not in record.getMessage() for record in caplog.records)
    assert CHANNEL_TOKEN not in caplog.text


# --- concurrent operations (simulated between the two transactions) --------------------


def direct_publisher(db: Conn, fake: FakeTelegram) -> tuple[ChannelPublisher, ConnFactory]:
    """A second caller (e.g. the admin bot) on the same database and fake Bot API."""

    @contextmanager
    def open_conn() -> Iterator[Conn]:
        with db.transaction():
            yield db

    return ChannelPublisher(make_settings(**CHANNEL_ENV), fake.channel_client()), open_conn


def test_update_while_the_post_is_deleted(api: TestClient, db: Conn, fake: FakeTelegram) -> None:
    event = published(api)
    post = send(api, event["id"]).json()["publication"]
    api.patch(f"/events/{event['id']}", json={"summary": "Güncel özet."})

    def deleted_meanwhile(body: dict[str, Any]) -> None:
        # What delete() records, committed while the edit is in flight.
        db.execute(
            "update app.publications set status = 'deleted', deleted_at = now(),"
            " updating_since = null where id = %s",
            (post["id"],),
        )

    fake.hooks["editMessageCaption"] = deleted_meanwhile
    response = update(api, event["id"])
    assert response.status_code == 409
    assert "changed while it was being updated" in response.json()["detail"]
    [row] = publications(db, event["id"])
    assert (row["status"], row["content_version"]) == ("deleted", 1)  # not resurrected
    assert ("admin_ui", "telegram_update", "conflict") in audit(db, event["id"])


def test_update_after_another_update_took_over(
    api: TestClient, db: Conn, fake: FakeTelegram
) -> None:
    event = published(api)
    post = send(api, event["id"]).json()["publication"]
    api.patch(f"/events/{event['id']}", json={"summary": "Güncel özet."})

    def edited_meanwhile(body: dict[str, Any]) -> None:
        db.execute(
            "update app.publications set status = 'edited', edited_at = now(),"
            " content_version = 2, updating_since = null where id = %s",
            (post["id"],),
        )

    fake.hooks["editMessageCaption"] = edited_meanwhile
    response = update(api, event["id"])
    assert response.status_code == 409
    [row] = publications(db, event["id"])
    assert (row["status"], row["content_version"]) == ("edited", 2)  # the other result stays
    assert ("admin_ui", "telegram_update", "conflict") in audit(db, event["id"])


def test_a_second_update_is_refused_while_one_is_in_flight(
    api: TestClient, db: Conn, fake: FakeTelegram
) -> None:
    event = published(api)
    send(api, event["id"])
    api.patch(f"/events/{event['id']}", json={"summary": "Güncel özet."})
    publisher, open_conn = direct_publisher(db, fake)
    refusals: list[HTTPException] = []

    def second_update(body: dict[str, Any]) -> None:
        del fake.hooks["editMessageCaption"]
        try:
            publisher.update(open_conn, UUID(event["id"]), actor="admin_ui", expected_hash=None)
        except HTTPException as exc:
            refusals.append(exc)

    fake.hooks["editMessageCaption"] = second_update
    response = update(api, event["id"])
    assert response.status_code == 200, response.text
    assert response.json()["publication"]["content_version"] == 2
    [refusal] = refusals
    assert refusal.status_code == 409
    assert "being updated" in str(refusal.detail)
    assert len(fake.bodies("editMessageCaption")) == 1  # the message was edited once
    row = db.execute(
        "select updating_since from app.publications where event_id = %s", (event["id"],)
    ).fetchone()
    assert row is not None and row["updating_since"] is None  # claim released


def test_a_stale_update_claim_does_not_block(api: TestClient, db: Conn, fake: FakeTelegram) -> None:
    event = published(api)
    send(api, event["id"])
    api.patch(f"/events/{event['id']}", json={"summary": "Güncel özet."})
    db.execute(
        "update app.publications set updating_since = now() - interval '11 minutes'"
        " where event_id = %s",
        (event["id"],),
    )
    assert update(api, event["id"]).status_code == 200


def test_delete_while_the_post_is_deleted_elsewhere(
    api: TestClient, db: Conn, fake: FakeTelegram
) -> None:
    event = published(api)
    post = send(api, event["id"]).json()["publication"]

    def deleted_meanwhile(body: dict[str, Any]) -> None:
        db.execute(
            "update app.publications set status = 'deleted', deleted_at = now() where id = %s",
            (post["id"],),
        )

    fake.hooks["deleteMessage"] = deleted_meanwhile
    response = delete(api, event["id"], post["id"])
    assert response.status_code == 409
    assert ("admin_ui", "telegram_delete", "conflict") in audit(db, event["id"])


# --- configuration ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("env", "problem"),
    [
        ({}, "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID"),
        ({**CHANNEL_ENV, "WEB_BASE_URL": None}, "Set WEB_BASE_URL"),
        ({**CHANNEL_ENV, "WEB_BASE_URL": "http://127.0.0.1:3000"}, "must be an https URL"),
        ({**CHANNEL_ENV, "TELEGRAM_BOT_TOKEN": "not-a-token"}, "invalid format"),
    ],
)
def test_not_configured(db: Conn, fake: FakeTelegram, env: dict[str, Any], problem: str) -> None:
    # The token format check runs only when the app builds the client itself.
    injected = fake.channel_client() if env.get("TELEGRAM_BOT_TOKEN") == CHANNEL_TOKEN else None
    app = create_app(
        make_settings(**{"TELEGRAM_BOT_TOKEN": None, "TELEGRAM_CHANNEL_ID": None, **env}),
        revalidator=RecordingRevalidator(),
        telegram_client=injected,
    )
    api = make_client(app, db)
    event = published(api)
    state = preview(api, event["id"])
    assert state["configured"] is False
    assert problem in state["config_problem"]
    assert state["can_send"] is False
    response = send(api, event["id"], state["content_hash"])
    assert response.status_code == 409
    assert problem in response.json()["detail"]
    assert fake.calls == []


def test_channel_routes_require_the_token() -> None:
    app = create_app(make_settings())
    anon = TestClient(app, base_url=BASE_URL)
    event_id = "00000000-0000-4000-8000-000000000000"
    assert anon.get("/telegram/channel/posts").status_code == 401
    assert anon.get(f"/telegram/channel/events/{event_id}/preview").status_code == 401
    response = anon.post(
        f"/telegram/channel/events/{event_id}/send", json={"content_hash": "a" * 64}
    )
    assert response.status_code == 401


def test_openapi_operation_ids(api: TestClient) -> None:
    paths = api.get("/openapi.json").json()["paths"]
    ids = {op["operationId"] for path in paths.values() for op in path.values()}
    assert {
        "list_channel_posts",
        "preview_channel_post",
        "list_channel_post_history",
        "send_channel_post",
        "update_channel_post",
        "delete_channel_post",
        "resolve_channel_post",
    } <= ids
    assert "502" in paths["/telegram/channel/events/{event_id}/send"]["post"]["responses"]


def test_force_status_published_events_are_listed(api: TestClient, db: Conn) -> None:
    event = create_event(api)
    force_status(db, event["id"], "published")
    items = api.get("/telegram/channel/posts", params={"limit": 200}).json()["items"]
    assert event["id"] in [item["event_id"] for item in items]

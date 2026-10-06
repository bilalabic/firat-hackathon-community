"""Units for channel publishing: Bot API parameters of the new client methods, error
mapping, and the admin bot's channel tokens and buttons."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx2
import pytest

from fhc_api.admin_bot import codec, messages
from fhc_api.admin_bot.context import current_token
from fhc_api.publishing.service import describe_error, is_photo_error
from fhc_api.telegram.client import (
    MEDIA_TIMEOUT_S,
    TelegramAPIError,
    TelegramClient,
    TelegramNetworkError,
    TelegramResponseError,
)
from tests.fake_telegram import CHANNEL_LEAK_MARKER, CHANNEL_TOKEN

MESSAGE = {"message_id": 7, "date": 1, "chat": {"id": -100, "type": "channel"}}


def recording_client(result: object) -> tuple[TelegramClient, list[httpx2.Request]]:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"ok": True, "result": result})

    transport = httpx2.MockTransport(handler)
    return TelegramClient(CHANNEL_TOKEN, client=httpx2.Client(transport=transport)), seen


def body(request: httpx2.Request) -> object:
    return json.loads(request.content)


def test_send_photo_params_and_timeout() -> None:
    client, seen = recording_client(MESSAGE)
    message = client.send_photo("@ch", "https://x.org/card?v=1", caption="<b>x</b>")
    assert message.message_id == 7
    assert seen[0].url.path.endswith("/sendPhoto")
    assert body(seen[0]) == {
        "chat_id": "@ch",
        "photo": "https://x.org/card?v=1",
        "caption": "<b>x</b>",
        "parse_mode": "HTML",
    }
    assert seen[0].extensions["timeout"]["read"] == MEDIA_TIMEOUT_S


def test_edit_methods_params() -> None:
    client, seen = recording_client(MESSAGE)
    client.edit_message_caption(-100, 7, "c")
    client.edit_message_media(-100, 7, "https://x.org/card", caption="c")
    client.edit_message_text(-100, 7, "t", link_preview_options={"url": "https://x.org"})
    assert body(seen[0]) == {"chat_id": -100, "message_id": 7, "caption": "c", "parse_mode": "HTML"}
    assert body(seen[1]) == {
        "chat_id": -100,
        "message_id": 7,
        "media": {
            "type": "photo",
            "media": "https://x.org/card",
            "caption": "c",
            "parse_mode": "HTML",
        },
    }
    assert body(seen[2]) == {
        "chat_id": -100,
        "message_id": 7,
        "text": "t",
        "parse_mode": "HTML",
        "link_preview_options": {"url": "https://x.org"},
    }


def test_send_message_with_a_link_preview() -> None:
    client, seen = recording_client(MESSAGE)
    client.send_message(-100, "t", link_preview_options={"url": "https://x.org"})
    assert body(seen[0])["link_preview_options"] == {"url": "https://x.org"}  # type: ignore[index]


def test_delete_message() -> None:
    client, seen = recording_client(True)
    client.delete_message(-100, 7)
    assert body(seen[0]) == {"chat_id": -100, "message_id": 7}
    unexpected, _ = recording_client({"no": "bool"})
    with pytest.raises(TelegramResponseError):
        unexpected.delete_message(-100, 7)


def api_error(code: int, description: str, retry_after: int | None = None) -> TelegramAPIError:
    return TelegramAPIError("sendPhoto", code, description, retry_after)


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("Bad Request: wrong file identifier/HTTP URL specified", True),
        ("Bad Request: failed to get HTTP URL content", True),
        ("Bad Request: wrong type of the web page content", True),
        ("Bad Request: PHOTO_INVALID_DIMENSIONS", True),
        ("Bad Request: IMAGE_PROCESS_FAILED", True),
        ("Bad Request: chat not found", False),
        ("Bad Request: can't parse entities: unexpected end tag", False),
        ("Bad Request: message is too long", False),
    ],
)
def test_photo_errors(description: str, expected: bool) -> None:
    assert is_photo_error(api_error(400, description)) is expected


def test_only_400_counts_as_a_photo_error() -> None:
    assert not is_photo_error(api_error(403, "Forbidden: photo"))
    assert not is_photo_error(TelegramNetworkError("Telegram sendPhoto timed out."))


def test_describe_error() -> None:
    assert "TELEGRAM_BOT_TOKEN" in describe_error(api_error(401, "Unauthorized"))
    assert "TELEGRAM_BOT_TOKEN" in describe_error(api_error(404, "Not Found"))
    assert "administrator" in describe_error(api_error(403, "Forbidden: bot was kicked"))
    assert "administrator" in describe_error(api_error(400, "Bad Request: not enough rights"))
    assert "TELEGRAM_CHANNEL_ID" in describe_error(api_error(400, "Bad Request: chat not found"))
    assert "retry after 3 s" in describe_error(api_error(429, "Too Many Requests", 3))
    assert "T-1" in describe_error(api_error(400, "Bad Request: message can't be deleted"))
    assert describe_error(api_error(400, "Bad Request: other")) == (
        "Telegram refused the request (400: Bad Request: other)."
    )
    timeout = TelegramNetworkError("Telegram sendPhoto timed out.")
    assert "check the channel" in describe_error(timeout, sending=True)
    assert describe_error(timeout) == "Telegram sendPhoto timed out."


def test_network_errors_never_contain_the_token() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError(f"cannot reach {request.url}")

    client = TelegramClient(
        CHANNEL_TOKEN, client=httpx2.Client(transport=httpx2.MockTransport(handler))
    )
    with pytest.raises(TelegramNetworkError) as info:
        client.send_photo("@ch", "https://x.org/card", caption="c")
    assert CHANNEL_LEAK_MARKER not in describe_error(info.value, sending=True)
    assert CHANNEL_LEAK_MARKER not in repr(info.value)


# --- admin bot: channel offers -----------------------------------------------------------


def test_channel_tokens_depend_on_the_post() -> None:
    at = datetime(2026, 10, 7, 12, tzinfo=UTC)
    no_post = current_token("channel_post", "published", at)
    assert no_post == codec.channel_token(at, "")
    assert current_token("channel_post", "published", at, "id:1") is None
    assert current_token("channel_update", "published", at) is None
    v1 = current_token("channel_update", "published", at, "id:1")
    v2 = current_token("channel_update", "published", at, "id:2")
    assert v1 is not None and v2 is not None and v1 != v2
    assert current_token("channel_update", "published", at + timedelta(seconds=1), "id:1") != v1
    assert current_token("channel_post", "approved", at) is None
    with pytest.raises(ValueError, match="timezone-aware"):
        codec.channel_token(datetime(2026, 1, 1), "")


@pytest.mark.parametrize(
    "action",
    ["channel_post", "channel_post_confirm", "channel_update", "channel_update_confirm"],
)
def test_channel_buttons_round_trip(action: codec.Action) -> None:
    callback = codec.Callback(action, "event", uuid4(), "0123abcd")
    assert codec.decode(codec.encode(callback)) == callback
    assert codec.decode(codec.encode(callback).replace(":e:", ":c:")) is None


def test_channel_keyboards() -> None:
    entity = uuid4()
    labels = {
        layout: [
            button["text"]
            for row in messages.keyboard(layout, "event", entity, "0123abcd")["inline_keyboard"]
            for button in row
        ]
        for layout in ("channel_post", "channel_post_confirm", "channel_update")
    }
    assert labels == {
        "channel_post": ["📣 Post to channel", "Later"],
        "channel_post_confirm": ["📣 Confirm post", "Cancel"],
        "channel_update": ["🔄 Update channel post", "Later"],
    }


def test_channel_offer_text_is_escaped() -> None:
    event = {"title": "A <b> & C", "start_date": None, "official_url": "https://x.org"}
    text = messages.channel_text(event, "channel_post")
    assert "<b>A &lt;b&gt; &amp; C</b>" in text
    assert "Post it to the channel?" in text
    assert "Update the channel post" in messages.channel_text(event, "channel_update")

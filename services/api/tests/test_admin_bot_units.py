"""Admin bot units: codec, configuration, message building, client additions, redaction."""

import json
import logging
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, get_args
from uuid import uuid4

import httpx2
import pytest

from fhc_api.admin_bot import codec, messages
from fhc_api.admin_bot.context import current_token
from fhc_api.admin_bot.runner import describe_error
from fhc_api.admin_bot.settings import AdminBotConfigError, is_enabled, load_config, parse_admin_ids
from fhc_api.common.audit import EntityType
from fhc_api.review.models import Signal
from fhc_api.telegram.client import (
    TelegramAPIError,
    TelegramClient,
    TelegramNetworkError,
)
from tests.conftest import make_settings
from tests.fake_telegram import ADMIN_LEAK_MARKER, ADMIN_TOKEN

# --- codec ---------------------------------------------------------------------------


def all_callbacks() -> list[codec.Callback]:
    callbacks = []
    for action in get_args(codec.Action):
        entity_types: list[EntityType] = (
            ["community_application", "team_application"]
            if action in codec.KIND_ACTIONS["application"]
            else ["event"]
        )
        for entity_type in entity_types:
            callbacks.append(codec.Callback(action, entity_type, uuid4(), "0123abcd"))
    return callbacks


@pytest.mark.parametrize("callback", all_callbacks(), ids=lambda c: f"{c.action}-{c.entity_type}")
def test_callback_data_round_trips_within_64_bytes(callback: codec.Callback) -> None:
    data = codec.encode(callback)
    assert 1 <= len(data.encode()) <= codec.CALLBACK_DATA_MAX_BYTES
    assert data.startswith("v1:")
    assert codec.decode(data) == callback


@pytest.mark.parametrize(
    "data",
    [
        None,
        "",
        "v2:ap:e:" + "0" * 32 + ":0123abcd",
        "v1:zz:e:" + "0" * 32 + ":0123abcd",  # unknown action
        "v1:ap:x:" + "0" * 32 + ":0123abcd",  # unknown entity type
        "v1:ap:c:" + "0" * 32 + ":0123abcd",  # event action on an application
        "v1:ac:e:" + "0" * 32 + ":0123abcd",  # application action on an event
        "v1:ap:e:" + "0" * 31 + ":0123abcd",  # short id
        "v1:ap:e:" + "0" * 32 + ":0123ABCD",  # uppercase token
        "v1:ap:e:" + "0" * 32 + ":0123abcd:extra",
    ],
)
def test_decode_rejects_malformed_data(data: str | None) -> None:
    assert codec.decode(data) is None


def test_encode_rejects_a_bad_token() -> None:
    with pytest.raises(ValueError):
        codec.encode(codec.Callback("approve", "event", uuid4(), "not-hex!"))


def test_state_tokens() -> None:
    at = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
    token = codec.state_token(at)
    assert len(token) == 8
    # Same instant in another zone -> same token; another instant -> another token.
    assert codec.state_token(at.astimezone(timezone(timedelta(hours=3)))) == token
    assert codec.state_token(at + timedelta(microseconds=1)) != token
    with pytest.raises(ValueError):
        codec.state_token(datetime(2026, 10, 6))  # naive on purpose


def test_current_token_depends_on_kind_and_status() -> None:
    at = datetime(2026, 10, 6, tzinfo=UTC)
    assert current_token("review", "in_review", at) == codec.state_token(at)
    assert current_token("review", "approved", at) is None
    assert current_token("publish", "approved", at) == codec.state_token(at)
    assert current_token("publish", None, None) is None
    assert current_token("application", "new", at) == codec.state_token(at)
    assert current_token("application", "new", None) is None
    assert current_token("application", "spam", None) is None


# --- configuration -------------------------------------------------------------------


def bot_settings(**overrides: Any) -> Any:
    values = {
        "TELEGRAM_ADMIN_ENABLED": "true",
        "TELEGRAM_ADMIN_BOT_TOKEN": ADMIN_TOKEN,
        "TELEGRAM_ADMIN_USER_IDS": "1111",
        **overrides,
    }
    return make_settings(**values)


def test_disabled_by_default() -> None:
    assert not is_enabled(make_settings())
    assert not is_enabled(make_settings(TELEGRAM_ADMIN_ENABLED="false"))
    assert not is_enabled(make_settings(TELEGRAM_ADMIN_ENABLED="0"))
    assert is_enabled(make_settings(TELEGRAM_ADMIN_ENABLED="TRUE"))


def test_load_config_defaults() -> None:
    config = load_config(bot_settings(TELEGRAM_ADMIN_USER_IDS=" 1111, 2222 3333 "))
    assert config.admin_ids == {1111, 2222, 3333}
    assert config.max_press_age_h == 12
    assert config.scan_interval_s == 60
    assert ADMIN_LEAK_MARKER not in repr(config)
    assert "1111" not in repr(config)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"TELEGRAM_ADMIN_ENABLED": "maybe"}, "must be true or false"),
        ({"TELEGRAM_ADMIN_BOT_TOKEN": None}, "TELEGRAM_ADMIN_BOT_TOKEN is not set"),
        ({"TELEGRAM_ADMIN_USER_IDS": None}, "is empty"),
        ({"TELEGRAM_ADMIN_USER_IDS": "@bilal"}, "numeric"),
        ({"TELEGRAM_ADMIN_USER_IDS": "-100123"}, "numeric"),
        ({"TELEGRAM_ADMIN_MAX_PRESS_AGE_H": "0"}, "between"),
        ({"TELEGRAM_ADMIN_MAX_PRESS_AGE_H": "nan"}, "between"),
        ({"TELEGRAM_ADMIN_SCAN_INTERVAL_S": "abc"}, "between"),
        ({"TELEGRAM_ADMIN_SCAN_INTERVAL_S": "1"}, "between"),
        ({"TELEGRAM_BOT_TOKEN": ADMIN_TOKEN}, "separate admin bot"),
    ],
)
def test_load_config_errors(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(AdminBotConfigError, match=message) as info:
        load_config(bot_settings(**overrides))
    assert ADMIN_LEAK_MARKER not in str(info.value)


def test_parse_admin_ids() -> None:
    assert parse_admin_ids("42") == {42}
    with pytest.raises(AdminBotConfigError):
        parse_admin_ids(" , ")


# --- messages ------------------------------------------------------------------------


def event_row(**overrides: Any) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "title": "Hack <b>&</b> Win",
        "start_date": "2026-11-05",
        "end_date": "2026-11-06",
        "application_deadline": None,
        "format": "in_person",
        "city": "Elazığ",
        "country": "TR",
        "official_url": 'https://example.com/a?b=1&c="x"',
        **overrides,
    }


def test_review_text_escapes_everything() -> None:
    signals = [
        Signal(
            key="dates_coherent", status="pass", detail="dates are coherent", blocks_approval=False
        ),
        Signal(key="possible_duplicate", status="warn", detail="dup of <x>", blocks_approval=False),
        Signal(key="official_url_reachable", status="fail", detail="bad", blocks_approval=True),
    ]
    text = messages.review_text(event_row(), signals)
    assert "<b>Hack &lt;b&gt;&amp;&lt;/b&gt; Win</b>" in text
    assert 'href="https://example.com/a?b=1&amp;c=&quot;x&quot;"' in text
    assert "Deadline: not set" in text
    assert "Elazığ, TR" in text
    assert (
        "✓ Dates" in text and "⚠ Duplicates: dup of &lt;x&gt;" in text and "✗ Official URL" in text
    )
    assert len(text) < 4096


def test_unsafe_official_url_is_not_linked() -> None:
    text = messages.publish_text(event_row(official_url="javascript:alert(1)"))
    assert "href" not in text
    assert "javascript" not in text


def test_application_text_has_no_personal_details() -> None:
    row = {
        "full_name": "Ayşe <Yılmaz> Demir",
        "preferred_channel": "whatsapp",
        "phone": "+905551112233",
        "telegram_username": "ayse_y",
        "message": "secret message",
        "university": "Fırat",
    }
    text = messages.application_text("community_application", row)
    assert "Ayşe" in text
    assert "WhatsApp" in text
    for private in ("Yılmaz", "Demir", "+90555", "ayse_y", "secret", "Fırat"):
        assert private not in text
    team = messages.application_text("team_application", {"full_name": "<script>"})
    assert "&lt;script&gt;" in team
    assert "Channel" not in team


def test_keyboards_use_valid_callback_data() -> None:
    entity_id = uuid4()
    keyboard = messages.keyboard("review", "event", entity_id, "0123abcd")
    labels = [button["text"] for row in keyboard["inline_keyboard"] for button in row]
    assert labels == ["✅ Approve", "✏️ Request changes", "⛔ Reject"]
    for row in keyboard["inline_keyboard"]:
        for button in row:
            decoded = codec.decode(button["callback_data"])
            assert decoded is not None and decoded.entity_id == entity_id


# --- client additions ----------------------------------------------------------------


def recording_client(result: object) -> tuple[TelegramClient, list[httpx2.Request]]:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"ok": True, "result": result})

    return (
        TelegramClient(ADMIN_TOKEN, client=httpx2.Client(transport=httpx2.MockTransport(handler))),
        seen,
    )


def test_get_updates_sends_long_poll_params_and_parses_updates() -> None:
    client, seen = recording_client(
        [
            {
                "update_id": 7,
                "callback_query": {
                    "id": "q",
                    "from": {"id": 1, "is_bot": False, "first_name": "A"},
                    "chat_instance": "c",
                    "data": "x",
                    "message": {"message_id": 3, "date": 0, "chat": {"id": 1, "type": "private"}},
                },
            },
            {"update_id": 8, "edited_message": {"message_id": 1}},  # ignored type
        ]
    )
    updates = client.get_updates(offset=7, timeout_s=10, allowed_updates=["message"])
    assert [u.update_id for u in updates] == [7, 8]
    assert updates[0].callback_query is not None
    assert updates[0].callback_query.from_.id == 1
    assert updates[0].callback_query.message is not None  # InaccessibleMessage parses (date 0)
    assert json.loads(seen[0].content) == {
        "timeout": 10,
        "allowed_updates": ["message"],
        "offset": 7,
    }
    assert seen[0].extensions["timeout"]["read"] == 20


def test_send_message_params() -> None:
    client, seen = recording_client(
        {"message_id": 5, "date": 1, "chat": {"id": 1, "type": "private"}, "text": "t"}
    )
    message = client.send_message(
        1, "<b>x</b>", reply_markup={"force_reply": True}, reply_to_message_id=4
    )
    assert message.message_id == 5
    assert json.loads(seen[0].content) == {
        "chat_id": 1,
        "text": "<b>x</b>",
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
        "reply_markup": {"force_reply": True},
        "reply_parameters": {"message_id": 4, "allow_sending_without_reply": True},
    }


def test_edit_and_answer_params() -> None:
    client, seen = recording_client(True)
    client.edit_message_reply_markup(1, 2, None)
    client.answer_callback_query("q", "x" * 300)
    assert json.loads(seen[0].content) == {"chat_id": 1, "message_id": 2}
    assert json.loads(seen[1].content) == {"callback_query_id": "q", "text": "x" * 200}


def test_new_methods_keep_the_token_out_of_logs_and_errors(
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError(f"cannot reach {request.url}")

    client = TelegramClient(
        ADMIN_TOKEN, client=httpx2.Client(transport=httpx2.MockTransport(handler))
    )
    with caplog.at_level(logging.DEBUG), pytest.raises(TelegramNetworkError) as info:
        client.send_message(1, "hi")
    for text in (str(info.value), repr(info.value), describe_error(info.value), repr(client)):
        assert ADMIN_LEAK_MARKER not in text
    assert all(ADMIN_LEAK_MARKER not in record.getMessage() for record in caplog.records)


def test_describe_error_hides_database_details() -> None:
    import psycopg

    error = psycopg.errors.CheckViolation("Failing row contains (secret personal data)")
    assert "secret" not in describe_error(error)
    api_error = TelegramAPIError("getMe", 401, "Unauthorized", None)
    assert "rejected TELEGRAM_ADMIN_BOT_TOKEN" in describe_error(api_error)
    assert "only one admin API" in describe_error(
        TelegramAPIError("getUpdates", 409, "Conflict", None)
    )

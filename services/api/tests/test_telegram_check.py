from typing import Any

import httpx2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fhc_api.telegram.check import TelegramCheckResult, run_telegram_check
from fhc_api.telegram.client import TelegramClient
from fhc_api.telegram.router import build_telegram_router

# Obviously fake, format-valid token; leak assertions look for LEAK_MARKER.
LEAK_MARKER = "FakeTestOnlyNotARealBotSecret_0123"
TOKEN = f"123456789:{LEAK_MARKER}"
BOT = {"id": 42, "is_bot": True, "first_name": "FHC", "username": "fhc_bot"}
CHANNEL = {"id": -1001234567890, "type": "channel", "title": "Fırat Hackathon"}
ALL_RIGHTS = {"can_post_messages": True, "can_edit_messages": True, "can_delete_messages": True}


def ok(result: object) -> httpx2.Response:
    return httpx2.Response(200, json={"ok": True, "result": result})


def fail(code: int, description: str) -> httpx2.Response:
    return httpx2.Response(code, json={"ok": False, "error_code": code, "description": description})


def admin(**rights: bool) -> dict[str, Any]:
    return {"status": "administrator", "user": BOT, "can_manage_chat": True, **rights}


def fake_telegram(
    get_me: httpx2.Response | None = None,
    get_chat: httpx2.Response | None = None,
    get_chat_member: httpx2.Response | None = None,
) -> TelegramClient:
    responses = {
        "getMe": get_me or ok(BOT),
        "getChat": get_chat or ok(CHANNEL),
        "getChatMember": get_chat_member or ok(admin(**ALL_RIGHTS)),
    }

    def handler(request: httpx2.Request) -> httpx2.Response:
        return responses[request.url.path.rsplit("/", 1)[1]]

    return TelegramClient(TOKEN, client=httpx2.Client(transport=httpx2.MockTransport(handler)))


def check(client: TelegramClient | None, channel: str | None = "@fhc") -> TelegramCheckResult:
    result = run_telegram_check(client, channel)
    assert LEAK_MARKER not in result.model_dump_json()
    return result


def test_ok() -> None:
    result = check(fake_telegram())
    assert result.status == "ok"
    assert result.bot_username == "fhc_bot"
    assert result.chat_title == "Fırat Hackathon"
    assert result.chat_type == "channel"
    assert result.missing_rights == []


def test_creator_counts_as_all_rights() -> None:
    member = ok({"status": "creator", "user": BOT, "is_anonymous": False})
    assert check(fake_telegram(get_chat_member=member)).status == "ok"


@pytest.mark.parametrize(
    ("client_present", "channel"), [(False, "@fhc"), (True, None), (True, " "), (False, None)]
)
def test_not_configured(client_present: bool, channel: str | None) -> None:
    client = fake_telegram() if client_present else None
    assert check(client, channel).status == "not_configured"


@pytest.mark.parametrize(
    "response", [fail(401, "Unauthorized"), fail(404, "Not Found")], ids=["401", "404"]
)
def test_invalid_token(response: httpx2.Response) -> None:
    assert check(fake_telegram(get_me=response)).status == "invalid_token"


def test_chat_not_found() -> None:
    result = check(fake_telegram(get_chat=fail(400, "Bad Request: chat not found")))
    assert result.status == "chat_not_found"
    assert result.bot_username == "fhc_bot"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"get_chat": fail(403, "Forbidden: bot is not a member of the channel chat")},
        {"get_chat_member": fail(403, "Forbidden: bot was kicked from the channel chat")},
        {"get_chat_member": fail(400, "Bad Request: user not found")},
        {"get_chat_member": ok({"status": "left", "user": BOT})},
        {"get_chat_member": ok({"status": "member", "user": BOT})},
        {"get_chat_member": ok({"status": "kicked", "user": BOT, "until_date": 0})},
    ],
    ids=["getChat-403", "member-403", "user-not-found", "left", "member", "kicked"],
)
def test_bot_not_admin(kwargs: dict[str, httpx2.Response]) -> None:
    assert check(fake_telegram(**kwargs)).status == "bot_not_admin"


@pytest.mark.parametrize(
    ("rights", "missing"),
    [
        ({"can_post_messages": True}, ["can_edit_messages"]),
        (
            {"can_post_messages": False, "can_edit_messages": True, "can_delete_messages": True},
            ["can_post_messages"],
        ),
        ({}, ["can_post_messages", "can_edit_messages"]),
    ],
)
def test_missing_rights(rights: dict[str, bool], missing: list[str]) -> None:
    result = check(fake_telegram(get_chat_member=ok(admin(**rights))))
    assert result.status == "missing_rights"
    assert result.missing_rights == missing
    for right in missing:
        assert right in result.message


def test_missing_delete_right_is_reported_but_ok() -> None:
    rights = {"can_post_messages": True, "can_edit_messages": True}
    result = check(fake_telegram(get_chat_member=ok(admin(**rights))))
    assert result.status == "ok"
    assert result.missing_rights == []
    assert result.missing_optional_rights == ["can_delete_messages"]
    assert "can_delete_messages" in result.message
    # Information, not something to fix.
    assert "optional" in result.message
    assert "lacks" not in result.message


def test_excess_rights_are_reported_with_a_warning_but_ok() -> None:
    rights = {
        **ALL_RIGHTS,
        "can_change_info": True,
        "can_promote_members": True,
        "can_invite_users": False,
        "can_post_stories": True,
    }
    result = check(fake_telegram(get_chat_member=ok(admin(**rights))))
    assert result.status == "ok"
    assert result.excess_rights == ["can_change_info", "can_promote_members", "can_post_stories"]
    assert "Warning" in result.message
    assert "can_promote_members" in result.message
    # Implied by every administrator right, so never reported.
    assert "can_manage_chat" not in result.excess_rights


def test_excess_rights_are_also_reported_when_required_rights_are_missing() -> None:
    result = check(
        fake_telegram(get_chat_member=ok(admin(can_post_messages=True, can_restrict_members=True)))
    )
    assert result.status == "missing_rights"
    assert result.missing_rights == ["can_edit_messages"]
    assert result.excess_rights == ["can_restrict_members"]


def test_least_privilege_admin_has_no_excess_rights() -> None:
    result = check(fake_telegram())
    assert result.excess_rights == []
    assert result.message == "Bot token and required channel rights are OK."


@pytest.mark.parametrize("channel", ["@fhc", None])
def test_invalid_token_format_is_reported_before_anything_else(channel: str | None) -> None:
    result = run_telegram_check(None, channel, invalid_token_format=True)
    assert result.status == "invalid_token"
    assert "TELEGRAM_BOT_TOKEN has an invalid format" in result.message


def test_non_channel_chat_is_error() -> None:
    group = ok({"id": -100, "type": "supergroup", "title": "Group"})
    result = check(fake_telegram(get_chat=group))
    assert result.status == "error"
    assert "supergroup" in result.message


@pytest.mark.parametrize(
    "response",
    [fail(500, "Internal Server Error"), fail(400, "Bad Request: something else")],
)
def test_unexpected_errors(response: httpx2.Response) -> None:
    assert check(fake_telegram(get_chat=response)).status == "error"


def test_rate_limit_is_error_with_retry_hint() -> None:
    limited = httpx2.Response(
        429,
        json={
            "ok": False,
            "error_code": 429,
            "description": "Too Many Requests: retry after 5",
            "parameters": {"retry_after": 5},
        },
    )
    result = check(fake_telegram(get_me=limited))
    assert result.status == "error"
    assert "5 s" in result.message


def test_network_error_is_error_without_token() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError(f"cannot reach {request.url}", request=request)

    client = TelegramClient(TOKEN, client=httpx2.Client(transport=httpx2.MockTransport(handler)))
    result = check(client)
    assert result.status == "error"


def router_client(tg: TelegramClient | None, channel: str | None) -> TestClient:
    def get_client() -> TelegramClient | None:
        return tg

    app = FastAPI()
    app.include_router(build_telegram_router(get_client, channel))
    return TestClient(app)


def test_router_ok() -> None:
    response = router_client(fake_telegram(), "@fhc").get("/telegram/check")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert LEAK_MARKER not in response.text


def test_router_not_configured() -> None:
    body = router_client(None, None).get("/telegram/check").json()
    assert body["status"] == "not_configured"


def test_router_missing_rights() -> None:
    tg = fake_telegram(get_chat_member=ok(admin(can_post_messages=True)))
    body = router_client(tg, "@fhc").get("/telegram/check").json()
    assert body["status"] == "missing_rights"
    assert body["missing_rights"] == ["can_edit_messages"]


def test_router_operation_id() -> None:
    schema = router_client(None, None).get("/openapi.json").json()
    assert schema["paths"]["/telegram/check"]["get"]["operationId"] == "telegram_check"

import json
import logging
from collections.abc import Callable

import httpx2
import pytest

from fhc_api.telegram.client import (
    TelegramAPIError,
    TelegramClient,
    TelegramConfigError,
    TelegramError,
    TelegramNetworkError,
    TelegramResponseError,
)

# Obviously fake, format-valid token; leak assertions look for LEAK_MARKER.
LEAK_MARKER = "FakeTestOnlyNotARealBotSecret_0123"
TOKEN = f"123456789:{LEAK_MARKER}"

Handler = Callable[[httpx2.Request], httpx2.Response]


def make_client(handler: Handler) -> TelegramClient:
    return TelegramClient(TOKEN, client=httpx2.Client(transport=httpx2.MockTransport(handler)))


def ok(result: object) -> httpx2.Response:
    return httpx2.Response(200, json={"ok": True, "result": result})


def assert_no_token(exc: BaseException) -> None:
    for text in (str(exc), repr(exc), repr(exc.args)):
        assert LEAK_MARKER not in text
    assert exc.__cause__ is None
    assert exc.__context__ is None
    assert not any(isinstance(v, httpx2.Request | httpx2.URL) for v in vars(exc).values())


def test_get_me_posts_to_token_url_and_parses_user() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return ok({"id": 42, "is_bot": True, "first_name": "FHC", "username": "fhc_bot", "x": 1})

    user = make_client(handler).get_me()

    assert user.id == 42
    assert user.username == "fhc_bot"
    assert seen[0].method == "POST"
    assert str(seen[0].url) == f"https://api.telegram.org/bot{TOKEN}/getMe"


def test_get_chat_and_member_send_json_params() -> None:
    bodies: list[object] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        bodies.append(json.loads(request.content))
        if request.url.path.endswith("/getChat"):
            return ok({"id": -1001, "type": "channel", "title": "FHC"})
        return ok(
            {
                "status": "administrator",
                "user": {"id": 42, "is_bot": True, "first_name": "FHC"},
                "can_post_messages": True,
            }
        )

    client = make_client(handler)
    chat = client.get_chat("@fhc")
    member = client.get_chat_member(chat.id, 42)

    assert chat.title == "FHC"
    assert member.can_post_messages is True
    assert member.can_edit_messages is None
    assert bodies == [{"chat_id": "@fhc"}, {"chat_id": -1001, "user_id": 42}]


def test_api_error_is_mapped() -> None:
    client = make_client(
        lambda r: httpx2.Response(
            400, json={"ok": False, "error_code": 400, "description": "Bad Request: chat not found"}
        )
    )

    with pytest.raises(TelegramAPIError) as info:
        client.get_chat("@missing")

    assert info.value.error_code == 400
    assert info.value.description == "Bad Request: chat not found"
    assert info.value.method == "getChat"
    assert_no_token(info.value)


def test_retry_after_is_parsed() -> None:
    client = make_client(
        lambda r: httpx2.Response(
            429,
            json={
                "ok": False,
                "error_code": 429,
                "description": "Too Many Requests: retry after 7",
                "parameters": {"retry_after": 7},
            },
        )
    )

    with pytest.raises(TelegramAPIError) as info:
        client.get_me()
    assert info.value.retry_after == 7


@pytest.mark.parametrize(
    "exc_type", [httpx2.ConnectError, httpx2.ReadTimeout, httpx2.RemoteProtocolError]
)
def test_network_errors_do_not_leak_token(exc_type: type[httpx2.RequestError]) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        # Worst case: the transport error message itself contains the URL.
        raise exc_type(f"failed for {request.url}", request=request)

    with pytest.raises(TelegramNetworkError) as info:
        make_client(handler).get_me()
    assert_no_token(info.value)


def test_description_echoing_url_is_redacted() -> None:
    client = make_client(
        lambda r: httpx2.Response(
            404,
            json={"ok": False, "error_code": 404, "description": f"Not Found: {r.url}"},
        )
    )

    with pytest.raises(TelegramAPIError) as info:
        client.get_me()
    assert_no_token(info.value)
    assert "/bot<redacted>/getMe" in info.value.description


@pytest.mark.parametrize(
    "response",
    [
        httpx2.Response(502, text="<html>Bad Gateway</html>"),
        httpx2.Response(200, json=[1, 2]),
        httpx2.Response(200, json={"ok": True, "result": {"id": "not-an-int"}}),
    ],
)
def test_malformed_responses(response: httpx2.Response) -> None:
    with pytest.raises(TelegramResponseError) as info:
        make_client(lambda r: response).get_me()
    assert_no_token(info.value)


def test_repr_does_not_contain_token() -> None:
    client = make_client(lambda r: ok({}))
    assert LEAK_MARKER not in repr(client)
    assert LEAK_MARKER not in str(client)


@pytest.mark.parametrize(
    "token", ["", "abc", "123:short", f"{TOKEN}/../x", f"{TOKEN}?a=1", f" {TOKEN} x"]
)
def test_invalid_token_format_rejected_without_echo(token: str) -> None:
    with pytest.raises(TelegramConfigError) as info:
        TelegramClient(token)
    assert token.strip() == "" or token not in str(info.value)


def test_httpx2_request_log_is_redacted(caplog: pytest.LogCaptureFixture) -> None:
    client = make_client(lambda r: ok({"id": 1, "is_bot": True, "first_name": "b"}))

    with caplog.at_level(logging.DEBUG):
        client.get_me()

    assert caplog.records, "httpx2 should log the request at INFO"
    for record in caplog.records:
        assert LEAK_MARKER not in record.getMessage()
    assert any("/bot<redacted>/getMe" in r.getMessage() for r in caplog.records)


def test_errors_share_base_class() -> None:
    assert issubclass(TelegramAPIError, TelegramError)
    assert issubclass(TelegramNetworkError, TelegramError)
    assert issubclass(TelegramResponseError, TelegramError)
    assert issubclass(TelegramConfigError, TelegramError)
    assert issubclass(TelegramConfigError, ValueError)


def test_own_http_client_ignores_environment_proxies() -> None:
    # The request URL carries the token; it must never be sent through a proxy.
    client = TelegramClient(TOKEN)
    try:
        assert client._client.trust_env is False
    finally:
        client.close()

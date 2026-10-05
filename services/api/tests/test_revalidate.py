import json
import logging
from collections.abc import Callable

import httpx2
import pytest

from fhc_api.web.revalidate import WebRevalidator, event_tags
from tests.conftest import make_settings

SECRET = "revalidate-secret-value"


def revalidator(handler: httpx2.MockTransport | None = None, **overrides: str) -> WebRevalidator:
    settings = make_settings(
        **{"WEB_BASE_URL": "https://site.example/", "WEB_REVALIDATE_SECRET": SECRET, **overrides}
    )
    return WebRevalidator(settings, transport=handler)


def test_event_tags() -> None:
    assert event_tags("fhc-2026") == ["events", "event:fhc-2026"]


def test_posts_tags_with_bearer_secret() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json={"revalidated": True})

    revalidator(httpx2.MockTransport(handler)).revalidate(["events", "event:x"])

    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == "https://site.example/api/revalidate"
    assert request.headers["authorization"] == f"Bearer {SECRET}"
    assert json.loads(request.content) == {"tags": ["events", "event:x"]}


@pytest.mark.parametrize("unset", ["WEB_BASE_URL", "WEB_REVALIDATE_SECRET"])
def test_disabled_without_configuration(unset: str) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise AssertionError("must not be called")

    settings = make_settings(
        **{"WEB_BASE_URL": "https://site.example", "WEB_REVALIDATE_SECRET": SECRET, unset: None}
    )
    target = WebRevalidator(settings, transport=httpx2.MockTransport(handler))

    assert not target.enabled
    target.revalidate(["events"])  # no request, no error


@pytest.mark.parametrize(
    "handler",
    [
        lambda request: httpx2.Response(500),
        lambda request: httpx2.Response(401),
        lambda request: httpx2.Response(308, headers={"location": "https://elsewhere.example/"}),
    ],
)
def test_http_failures_are_logged_without_the_secret(
    handler: Callable[[httpx2.Request], httpx2.Response], caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        revalidator(httpx2.MockTransport(handler)).revalidate(["events"])

    assert "web revalidation failed: HTTP" in caplog.text
    assert SECRET not in caplog.text


def test_network_errors_are_swallowed(caplog: pytest.LogCaptureFixture) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError(f"cannot connect, header was Bearer {SECRET}")

    with caplog.at_level(logging.DEBUG):
        revalidator(httpx2.MockTransport(handler)).revalidate(["events"])

    assert "web revalidation failed: ConnectError" in caplog.text
    assert SECRET not in caplog.text

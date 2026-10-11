"""Safe fetcher (CRAWLING_RESEARCH §5). No real network: DNS is a dict and HTTP is
httpx2.MockTransport."""

from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any

import httpx2
import pytest

from fhc_api.common.http import (
    MAX_REDIRECTS,
    USER_AGENT,
    BlockedUrlError,
    ContentTypeError,
    FetchError,
    SafeFetcher,
    check_url,
    is_public_address,
)

PUBLIC_IP = "93.184.215.14"
PUBLIC_IP_2 = "93.184.215.15"
Handler = Callable[[httpx2.Request], httpx2.Response]


def resolver_for(table: Mapping[str, Sequence[str]]) -> Callable[[str, int], Sequence[str]]:
    def resolve(host: str, port: int) -> Sequence[str]:
        if host not in table:
            raise OSError("name not known")
        return table[host]

    return resolve


def fetcher(
    handler: Handler, dns: Mapping[str, Sequence[str]] | None = None, **kwargs: Any
) -> SafeFetcher:
    return SafeFetcher(
        resolver=resolver_for(dns if dns is not None else {"example.com": [PUBLIC_IP]}),
        transport=httpx2.MockTransport(handler),
        **kwargs,
    )


def html(body: bytes = b"<html></html>", status: int = 200) -> httpx2.Response:
    return httpx2.Response(
        status, headers={"content-type": "text/html; charset=utf-8"}, content=body
    )


def never_called(request: httpx2.Request) -> httpx2.Response:
    raise AssertionError(f"no request expected, got {request.url}")


# --- address classification ---------------------------------------------------------


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "127.1.2.3",
        "10.0.0.1",
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.1",
        "169.254.169.254",  # cloud metadata
        "100.64.0.1",  # carrier-grade NAT
        "100.100.100.200",  # Alibaba metadata (inside 100.64/10)
        "0.0.0.0",  # noqa: S104 (test data)
        "224.0.0.1",  # multicast
        "255.255.255.255",
        "::1",
        "::",
        "fc00::1",
        "fd00:ec2::254",  # AWS metadata over IPv6 (unique local)
        "fe80::1",
        "fe80::1%eth0",
        "::ffff:127.0.0.1",  # IPv4-mapped loopback
        "::ffff:169.254.169.254",
        "ff02::1",
        "2001:db8::1",  # documentation range
        "64:ff9b::7f00:1",  # NAT64 -> 127.0.0.1
        "64:ff9b::a9fe:a9fe",  # NAT64 -> 169.254.169.254
        "64:ff9b::a00:1",  # NAT64 -> 10.0.0.1
        "::7f00:1",  # IPv4-compatible 127.0.0.1
        "::808:808",  # IPv4-compatible is deprecated: blocked even for a public IPv4
        "::ffff:0:7f00:1",  # IPv4-translated 127.0.0.1
        "fec0::1",  # site-local (deprecated)
        "not-an-ip",
        "",
    ],
)
def test_non_public_addresses_are_blocked(address: str) -> None:
    assert not is_public_address(address)


@pytest.mark.parametrize(
    "address",
    [
        PUBLIC_IP,
        "1.1.1.1",
        "2606:4700:4700::1111",
        "64:ff9b::808:808",  # NAT64 -> 8.8.8.8 (IPv6-only networks with DNS64)
    ],
)
def test_public_addresses_are_allowed(address: str) -> None:
    assert is_public_address(address)


# --- static URL checks --------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("ftp://example.com/", "only http and https"),
        ("file:///etc/passwd", "only http and https"),
        ("javascript:alert(1)", "only http and https"),
        ("gopher://example.com/", "only http and https"),
        ("https://example.com:8443/", "only ports 80 and 443"),
        ("http://example.com:22/", "only ports 80 and 443"),
        ("https://user:pass@example.com/", "credentials"),
        ("https:///path-only", "no host"),
        ("http://[::1/", "malformed"),
    ],
)
def test_check_url_rejects(url: str, message: str) -> None:
    with pytest.raises(BlockedUrlError, match=message):
        check_url(url)


@pytest.mark.parametrize(
    "url", ["https://example.com/", "http://example.com:80/x", "https://example.com:443/"]
)
def test_check_url_accepts(url: str) -> None:
    check_url(url)


# --- DNS checks ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "addresses",
    [
        ["127.0.0.1"],
        ["10.1.2.3"],
        ["169.254.169.254"],
        ["::1"],
        [PUBLIC_IP, "192.168.0.10"],  # one internal answer is enough to refuse
    ],
)
def test_hosts_resolving_to_internal_addresses_are_blocked(addresses: list[str]) -> None:
    safe = fetcher(never_called, {"example.com": addresses})

    with pytest.raises(BlockedUrlError, match="non-public address"):
        safe.fetch("https://example.com/")


@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://[::1]/", "http://169.254.169.254/"])
def test_ip_literals_are_checked_without_dns(url: str) -> None:
    safe = fetcher(never_called, {})  # an empty DNS table: literals must not be resolved

    with pytest.raises(BlockedUrlError, match="non-public address"):
        safe.fetch(url)


def test_public_ip_literal_is_fetched() -> None:
    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.headers["host"])
        return html()

    fetcher(handler, {}).fetch(f"http://{PUBLIC_IP}/")

    assert seen == [PUBLIC_IP]


def test_unresolvable_host() -> None:
    with pytest.raises(FetchError, match="could not be resolved"):
        fetcher(never_called, {}).fetch("https://example.com/")


# --- request shape: pinned address, Host, SNI, User-Agent --------------------------


def test_connects_to_the_checked_address_with_original_host() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return html(b"hello")

    result = fetcher(handler).fetch("https://example.com/page?q=1")

    request = seen[0]
    assert request.url.host == PUBLIC_IP
    assert request.url.path == "/page"
    assert request.headers["host"] == "example.com"
    assert request.extensions["sni_hostname"] == "example.com"
    assert request.headers["user-agent"] == USER_AGENT
    assert result.status_code == 200
    assert result.body == b"hello"
    assert result.url == "https://example.com/page?q=1"
    assert result.content_type == "text/html"


def test_http_requests_have_no_sni() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return html()

    fetcher(handler).fetch("http://example.com/")

    assert "sni_hostname" not in seen[0].extensions


# --- redirects ----------------------------------------------------------------------


def redirect(location: str, status: int = 302) -> httpx2.Response:
    return httpx2.Response(status, headers={"location": location})


def test_redirects_are_followed_and_rechecked_per_hop() -> None:
    dns = {"example.com": [PUBLIC_IP], "www.example.org": [PUBLIC_IP_2]}
    hops: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        hops.append(f"{request.headers['host']}{request.url.path}")
        if request.url.path == "/start":
            return redirect("/relative", 301)
        if request.url.path == "/relative":
            return redirect("https://www.example.org/final", 308)
        return html(b"done")

    result = fetcher(handler, dns).fetch("https://example.com/start")

    assert hops == ["example.com/start", "example.com/relative", "www.example.org/final"]
    assert result.url == "https://www.example.org/final"
    assert result.redirects == 2


@pytest.mark.parametrize(
    "location",
    [
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://internal.example/",  # resolves to a private address
        "https://example.com:8443/",
        "ftp://example.com/",
        "http://[::1",  # malformed: httpx2 raises RemoteProtocolError -> FetchError
    ],
)
def test_redirect_to_a_blocked_target_is_refused(location: str) -> None:
    dns = {"example.com": [PUBLIC_IP], "internal.example": ["10.0.0.5"]}
    requests: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(str(request.url))
        return redirect(location)

    with pytest.raises(FetchError):
        fetcher(handler, dns).fetch("https://example.com/")
    assert len(requests) == 1  # the blocked hop is never requested


def test_redirect_limit() -> None:
    count = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        nonlocal count
        count += 1
        return redirect(f"/hop{count}")

    with pytest.raises(FetchError, match=f"more than {MAX_REDIRECTS} redirects"):
        fetcher(handler).fetch("https://example.com/")
    assert count == MAX_REDIRECTS + 1


def test_exactly_max_redirects_is_allowed() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        hop = int(request.url.path.removeprefix("/") or 0)
        return redirect(f"/{hop + 1}") if hop < MAX_REDIRECTS else html()

    assert fetcher(handler).fetch("https://example.com/").redirects == MAX_REDIRECTS


def test_redirect_without_location_is_returned_as_is() -> None:
    result = fetcher(lambda _: html(status=302)).fetch("https://example.com/")

    assert result.status_code == 302


# --- body limits and content types -------------------------------------------------


class EndlessStream(httpx2.SyncByteStream):
    def __init__(self) -> None:
        self.chunks_sent = 0

    def __iter__(self) -> Iterator[bytes]:
        while True:
            self.chunks_sent += 1
            yield b"x" * 100


def test_body_over_the_cap_is_refused_while_streaming() -> None:
    stream = EndlessStream()

    def handler(request: httpx2.Request) -> httpx2.Response:
        # No content-length: only the streamed count can stop it.
        return httpx2.Response(200, headers={"content-type": "text/html"}, stream=stream)

    with pytest.raises(FetchError, match="too large"):
        fetcher(handler, max_body_bytes=5_000).fetch("https://example.com/")
    assert stream.chunks_sent == 51  # stopped right after crossing the cap


def test_declared_content_length_over_the_cap_is_refused_before_reading() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200, headers={"content-type": "text/html", "content-length": "999999"}, content=b"x"
        )

    with pytest.raises(FetchError, match="too large"):
        fetcher(handler, max_body_bytes=1_000).fetch("https://example.com/")


def test_body_at_the_cap_is_accepted() -> None:
    body = b"x" * 1_000
    result = fetcher(lambda _: html(body), max_body_bytes=1_000).fetch("https://example.com/")

    assert result.body == body


@pytest.mark.parametrize(
    "content_type",
    ["text/html", "application/json", "application/ld+json", "text/xml", "image/png"],
)
def test_allowed_content_types(content_type: str) -> None:
    response = httpx2.Response(200, headers={"content-type": content_type}, content=b"{}")

    assert fetcher(lambda _: response).fetch("https://example.com/").content_type == content_type


@pytest.mark.parametrize(
    "content_type", ["application/octet-stream", "application/pdf", "text/javascript", ""]
)
def test_other_content_types_are_refused_when_reading_a_body(content_type: str) -> None:
    headers = {"content-type": content_type} if content_type else {}
    response = httpx2.Response(200, headers=headers, content=b"data")

    with pytest.raises(FetchError, match="not allowed"):
        fetcher(lambda _: response).fetch("https://example.com/")


def test_content_types_narrow_the_allow_list() -> None:
    response = httpx2.Response(200, headers={"content-type": "application/json"}, content=b"{}")

    with pytest.raises(ContentTypeError, match="'application/json' is not allowed"):
        fetcher(lambda _: response).fetch(
            "https://example.com/", content_types=frozenset({"text/html"})
        )


def test_content_types_cannot_widen_the_allow_list() -> None:
    response = httpx2.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF")

    with pytest.raises(ContentTypeError, match="'application/pdf' is not allowed"):
        fetcher(lambda _: response).fetch(
            "https://example.com/", content_types=frozenset({"application/pdf", "text/html"})
        )


def test_charset_from_the_content_type_header() -> None:
    response = httpx2.Response(
        200, headers={"content-type": "text/html; charset=windows-1254"}, content=b"x"
    )

    assert fetcher(lambda _: response).fetch("https://example.com/").charset == "windows-1254"
    assert fetcher(lambda _: html()).fetch("https://example.com/").charset == "utf-8"


def test_headers_only_fetch_skips_the_body_and_content_type_check() -> None:
    response = httpx2.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF")

    result = fetcher(lambda _: response).fetch("https://example.com/", read_body=False)

    assert result.body == b""
    assert result.status_code == 200


# --- transport errors ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (httpx2.ConnectTimeout("slow"), "timed out"),
        (httpx2.ReadTimeout("slow"), "timed out"),
        (httpx2.ConnectError("refused"), "request failed"),
    ],
)
def test_transport_errors_become_fetch_errors(error: Exception, message: str) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise error

    with pytest.raises(FetchError, match=message):
        fetcher(handler).fetch("https://example.com/")


# --- timeouts -----------------------------------------------------------------------


def test_per_phase_timeout_is_configurable() -> None:
    seen: list[object] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.extensions["timeout"])
        return html()

    fetcher(handler).fetch("https://example.com/")
    fetcher(handler, timeout=20.0).fetch("https://example.com/")

    assert seen == [
        {"connect": 10.0, "read": 10.0, "write": 10.0, "pool": 10.0},
        {"connect": 20.0, "read": 20.0, "write": 20.0, "pool": 20.0},
    ]


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_deadline_limits_the_redirect_chain() -> None:
    clock = FakeClock()
    hops: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        hops.append(request.url.path)
        clock.now += 30.0  # each hop is slow but within the per-phase timeout
        return redirect(f"/hop{len(hops)}", 302)

    with pytest.raises(FetchError, match="request timed out"):
        fetcher(handler, deadline=45.0, clock=clock).fetch("https://example.com/")

    assert hops == ["/", "/hop1"]  # the third hop is not started


def test_last_hop_gets_only_the_remaining_time() -> None:
    clock = FakeClock()
    seen: list[object] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.extensions["timeout"]["read"])
        if request.url.path == "/":
            clock.now += 40.0
            return redirect("/next", 302)
        return html()

    fetcher(handler, timeout=20.0, deadline=45.0, clock=clock).fetch("https://example.com/")

    assert seen == [20.0, 5.0]


def test_deadline_stops_a_slow_body() -> None:
    clock = FakeClock()

    class SlowStream(httpx2.SyncByteStream):
        def __iter__(self) -> Iterator[bytes]:
            for _ in range(10):
                clock.now += 10.0
                yield b"x"

    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, headers={"content-type": "text/html"}, stream=SlowStream())

    with pytest.raises(FetchError, match="request timed out"):
        fetcher(handler, deadline=45.0, clock=clock).fetch("https://example.com/")

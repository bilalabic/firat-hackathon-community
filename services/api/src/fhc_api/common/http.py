"""Safe outbound fetcher for untrusted URLs (CRAWLING_RESEARCH §5).

Rules, applied to the first URL and to every redirect hop:
- only `http`/`https`, only ports 80 and 443, no credentials in the URL;
- the host is resolved here, and the request is refused if ANY resolved address is
  private, loopback, link-local (cloud metadata), unique-local, multicast, reserved or
  otherwise not globally routable;
- the connection then goes to the checked address (pinned), with the original host in
  the `Host` header and as the TLS SNI/certificate name. A second DNS lookup by the
  HTTP stack, which a rebinding attacker could answer differently, never happens;
- redirects are followed manually, at most 5;
- 10 s connect/read/write/pool timeouts; when a body is read, a 5 MB cap on the decoded
  body (counted while streaming) and a content-type allow-list (HTML, JSON, XML, images).
  A headers-only fetch (reachability) reads no body and needs no allow-list.

Not covered: DNS resolution itself has no timeout (OS resolver), and there is no
overall wall-clock limit across hops (at most 6 hops x the per-phase timeouts).

Environment proxies are ignored (`trust_env=False`) so they cannot bypass the checks.
"""

import ipaddress
import socket
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import httpx2

MAX_REDIRECTS = 5
MAX_BODY_BYTES = 5 * 1024 * 1024
TIMEOUT_SECONDS = 10.0
DEFAULT_PORTS = {"http": 80, "https": 443}
USER_AGENT = (
    "FiratHackathonCommunityBot/0.1 "
    "(+https://github.com/bilalabic/firat-hackathon-community; event link check)"
)
ALLOWED_CONTENT_TYPES = frozenset(
    {
        "text/html",
        "application/xhtml+xml",
        "application/json",
        "application/ld+json",
        "application/xml",
        "text/xml",
        "application/rss+xml",
        "application/atom+xml",
    }
)
_REDIRECT_CODES = frozenset({301, 302, 303, 307, 308})

# Explicit list from CRAWLING_RESEARCH §5. `is_global` below already excludes all of
# these; the list documents intent and guards against stdlib classification changes.
_BLOCKED_NETWORKS = tuple(
    ipaddress.ip_network(cidr)
    for cidr in (
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "::1/128",
        "::/128",
        "fc00::/7",
        "fe80::/10",
    )
)

type Resolver = Callable[[str, int], Sequence[str]]


class FetchError(Exception):
    """The URL was refused or could not be fetched. The message is safe to show."""


class BlockedUrlError(FetchError):
    """The URL or one of its resolved addresses is not allowed."""


@dataclass(frozen=True)
class FetchResult:
    url: str  # final URL after redirects
    status_code: int
    content_type: str
    body: bytes
    redirects: int


def system_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


def is_public_address(address: str) -> bool:
    """True only for globally routable unicast addresses."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped  # ::ffff:127.0.0.1 is 127.0.0.1
    if any(ip in network for network in _BLOCKED_NETWORKS):
        return False
    return ip.is_global and not ip.is_multicast


def check_url(url: str | httpx2.URL) -> httpx2.URL:
    """Static checks (no DNS): scheme, port, host, no credentials."""
    try:
        parsed = httpx2.URL(url)
    except httpx2.InvalidURL as exc:
        raise BlockedUrlError("malformed URL") from exc
    if parsed.scheme not in DEFAULT_PORTS:
        raise BlockedUrlError("only http and https URLs are allowed")
    if not parsed.host:
        raise BlockedUrlError("URL has no host")
    if parsed.userinfo:
        raise BlockedUrlError("URLs with credentials are not allowed")
    if parsed.port is not None and parsed.port not in DEFAULT_PORTS.values():
        raise BlockedUrlError("only ports 80 and 443 are allowed")
    return parsed


def _resolve_public(url: httpx2.URL, resolver: Resolver) -> str:
    host = url.raw_host.decode("ascii")
    try:
        ipaddress.ip_address(host)
        addresses: Sequence[str] = [host]  # IP literal: nothing to resolve
    except ValueError:
        try:
            addresses = resolver(host, url.port or DEFAULT_PORTS[url.scheme])
        except (OSError, UnicodeError) as exc:
            raise FetchError("host could not be resolved") from exc
    if not addresses:
        raise FetchError("host could not be resolved")
    # Refuse if ANY address is internal: the HTTP stack must never get a chance to
    # pick it, and mixed answers are a DNS-rebinding signal.
    if not all(is_public_address(address) for address in addresses):
        raise BlockedUrlError("host resolves to a non-public address")
    return addresses[0]


def _content_type(response: httpx2.Response) -> str:
    return response.headers.get("content-type", "").split(";")[0].strip().lower()


def _allowed_content_type(content_type: str) -> bool:
    return content_type in ALLOWED_CONTENT_TYPES or content_type.startswith("image/")


class SafeFetcher:
    def __init__(
        self,
        *,
        resolver: Resolver = system_resolver,
        transport: httpx2.BaseTransport | None = None,
        max_body_bytes: int = MAX_BODY_BYTES,
    ) -> None:
        self._resolver = resolver
        self._transport = transport  # tests pass httpx2.MockTransport
        self._max_body_bytes = max_body_bytes

    def fetch(self, url: str, *, read_body: bool = True) -> FetchResult:
        """GET `url` following at most MAX_REDIRECTS checked redirects.

        With `read_body=False` only the status line and headers are read (reachability).
        """
        current = check_url(url)
        with httpx2.Client(
            transport=self._transport,
            timeout=httpx2.Timeout(TIMEOUT_SECONDS),
            follow_redirects=False,
            trust_env=False,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            for redirects in range(MAX_REDIRECTS + 1):
                request = self._pinned_request(client, current)
                try:
                    response = client.send(request, stream=True)
                except httpx2.TimeoutException as exc:
                    raise FetchError("request timed out") from exc
                except httpx2.HTTPError as exc:
                    raise FetchError(f"request failed ({type(exc).__name__})") from exc
                try:
                    location = response.headers.get("location")
                    if response.status_code in _REDIRECT_CODES and location:
                        # httpx2 already parsed Location while building
                        # `response.next_request`; a malformed one raised
                        # RemoteProtocolError in `send` above.
                        current = check_url(current.join(location))
                        continue
                    return self._result(response, current, redirects, read_body=read_body)
                finally:
                    response.close()
        raise FetchError(f"more than {MAX_REDIRECTS} redirects")

    def _pinned_request(self, client: httpx2.Client, url: httpx2.URL) -> httpx2.Request:
        address = _resolve_public(url, self._resolver)
        host = url.raw_host.decode("ascii")  # IDNA-encoded
        extensions = {"sni_hostname": host} if url.scheme == "https" else {}
        return client.build_request(
            "GET",
            url.copy_with(host=address),
            headers={"Host": url.netloc.decode("ascii")},
            extensions=extensions,
        )

    def _result(
        self, response: httpx2.Response, url: httpx2.URL, redirects: int, *, read_body: bool
    ) -> FetchResult:
        content_type = _content_type(response)
        body = b""
        if read_body:  # the allow-list guards what we ingest; headers alone are harmless
            if not _allowed_content_type(content_type):
                raise FetchError(f"content type {content_type or '(none)'!r} is not allowed")
            body = self._read_capped(response)
        return FetchResult(
            url=str(url),
            status_code=response.status_code,
            content_type=content_type,
            body=body,
            redirects=redirects,
        )

    def _read_capped(self, response: httpx2.Response) -> bytes:
        declared = response.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > self._max_body_bytes:
            raise FetchError("response body too large")
        chunks: list[bytes] = []
        size = 0
        try:
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > self._max_body_bytes:
                    raise FetchError("response body too large")
                chunks.append(chunk)
        except httpx2.TimeoutException as exc:
            raise FetchError("request timed out") from exc
        except httpx2.HTTPError as exc:
            raise FetchError(f"reading the response failed ({type(exc).__name__})") from exc
        return b"".join(chunks)

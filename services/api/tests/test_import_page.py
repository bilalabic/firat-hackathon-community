"""URL import, part A: page loading (JSON-LD, meta tags, main text, errors). No real
network: DNS is a dict and HTTP is httpx2.MockTransport. The fixtures in
fixtures/import/ are hand-written minimal pages."""

import json
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx2
import pytest

from fhc_api.common.http import SafeFetcher
from fhc_api.importing.models import MAX_TEXT_CHARS, PageContent, PageError, StructuredValue
from fhc_api.importing.page import (
    MIN_TEXT_CHARS,
    SNIPPET_MAX_CHARS,
    HtmlPageLoader,
    decode_html,
    parse_page,
)

FIXTURES = Path(__file__).parent / "fixtures" / "import"
PUBLIC_IP = "93.184.215.14"
NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
PAGE_URL = "https://example.org/hack"
FILLER = (
    "<p>This paragraph is filler text so that the page has enough readable content for the "
    "loader. It describes a hackathon where teams build software over a weekend, meet "
    "mentors, present a demo to the jury and receive feedback on their projects.</p>"
)
Handler = Callable[[httpx2.Request], httpx2.Response]


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def parse(markup: str, url: str = PAGE_URL, final_url: str | None = None) -> PageContent:
    return parse_page(markup, requested_url=url, final_url=final_url or url, fetched_at=NOW)


def jsonld_page(*blocks: Any, head: str = "") -> str:
    scripts = "".join(
        f'<script type="application/ld+json">{json.dumps(block)}</script>' for block in blocks
    )
    return f"<html><head>{head}{scripts}</head><body><main>{FILLER}</main></body></html>"


def event(**properties: Any) -> dict[str, Any]:
    return {"@context": "https://schema.org", "@type": "Event", "name": "Test Hack", **properties}


def values(page: PageContent) -> dict[str, object]:
    return {field: proposal.value for field, proposal in page.structured.items()}


def loader(
    handler: Handler, dns: dict[str, list[str]] | None = None, **kwargs: int
) -> HtmlPageLoader:
    table = dns if dns is not None else {"example.org": [PUBLIC_IP]}

    def resolve(host: str, port: int) -> list[str]:
        if host not in table:
            raise OSError("name not known")
        return table[host]

    fetcher = SafeFetcher(resolver=resolve, transport=httpx2.MockTransport(handler), **kwargs)
    return HtmlPageLoader(fetcher, now=lambda: NOW)


def respond(
    body: bytes, content_type: str = "text/html; charset=utf-8", status: int = 200
) -> Handler:
    return lambda _: httpx2.Response(status, headers={"content-type": content_type}, content=body)


# --- fixtures ----------------------------------------------------------------------


def test_event_jsonld_fixture() -> None:
    body = fixture("event_jsonld.html").encode("utf-8")

    page = loader(respond(body)).load_page(PAGE_URL)

    assert values(page) == {
        "title": "Example Hack 2026",
        "organizer": "Example Student Club",
        "summary": "A 48-hour student hackathon on climate data.",
        "start_date": date(2026, 11, 14),
        "end_date": date(2026, 11, 16),  # 21:30Z is 00:30 the next day in Istanbul
        "format": "in_person",
        "venue": "Example University Library",
        "city": "Elazığ",
        "country": "TR",
        "is_free": True,
        "application_url": "https://example.org/hack/apply",
    }
    assert {proposal.source for proposal in page.structured.values()} == {"jsonld"}
    assert page.structured["end_date"].snippet == "2026-11-15T21:30:00Z"
    assert page.structured["title"].snippet == "Example Hack 2026"
    assert page.title == "Example Hack 2026"  # og:title wins over <title>
    assert page.image_url == "https://cdn.example.org/hack/banner.png"
    assert page.requested_url == page.final_url == PAGE_URL
    assert page.fetched_at == NOW
    assert "48-hour student hackathon on open climate data" in page.text
    assert "30,000 TRY" in page.text  # tables are kept
    assert "opening and team forming" in page.text  # lists are kept
    assert "Copyright Example Events" not in page.text  # boilerplate is dropped
    assert not page.text_truncated


def test_graph_with_invalid_block_and_turkish_text() -> None:
    url = "https://ornek.edu.tr/hackathon"

    page = parse(fixture("graph_turkish.html"), url)

    assert values(page) == {
        "title": "Doğu Anadolu Yapay Zekâ Hackathonu",
        "organizer": "Örnek Üniversitesi Yapay Zekâ Kulübü",
        # The JSON-LD description is longer than 300 characters: og:description is used.
        "summary": "Üniversite öğrencileri için iki günlük yapay zekâ hackathonu: ekibini kur, "
        "çözümünü geliştir.",
        "start_date": date(2026, 12, 5),
        "end_date": date(2026, 12, 6),
        "format": "hybrid",
        "venue": "Mühendislik Fakültesi",
        "city": "Elazığ",
        "country": "TR",  # from the country name "Türkiye"
        # no application_url: the event's `url` is the page itself
    }
    assert page.structured["summary"].source == "meta"
    assert page.title == "Doğu Anadolu Yapay Zekâ Hackathonu"
    assert "Başvurular 20 Kasım'a kadar açıktır" in page.text


def test_meta_only_page() -> None:
    page = parse(fixture("meta_only.html"), "https://example.org/jam/")

    assert page.title == "Spring Builders Jam"  # empty og:title ignored, whitespace collapsed
    assert page.image_url == "https://example.org/img/jam.png"  # made absolute
    assert page.structured == {
        "summary": StructuredValue(
            value="A weekend build jam for first-time hackers.",
            source="meta",
            snippet="A weekend build jam for first-time hackers.",
        )
    }
    assert "mentors run short workshops" in page.text


def test_js_only_page_has_no_readable_content() -> None:
    with pytest.raises(PageError, match=r"no readable content.*JavaScript"):
        parse(fixture("js_only.html"))


# --- JSON-LD shapes -----------------------------------------------------------------


@pytest.mark.parametrize(
    "document",
    [
        [{"@type": "WebSite", "name": "Site"}, event()],  # top-level array
        {"@context": "https://schema.org", "@graph": [{"@type": "WebPage"}, event()]},
        {"@type": "WebPage", "mainEntity": event()},  # nested
        {"@type": "ItemList", "itemListElement": [{"@type": "ListItem", "item": event()}]},
        event(**{"@type": "https://schema.org/SocialEvent"}),  # IRI
        event(**{"@type": "schema:EducationEvent"}),  # prefixed
        event(**{"@type": ["Thing", "Hackathon"]}),  # list
        event(**{"@type": "BusinessEvent"}),
    ],
)
def test_event_is_found_in_any_shape(document: Any) -> None:
    assert values(parse(jsonld_page(document)))["title"] == "Test Hack"


@pytest.mark.parametrize(
    "block",
    [
        "{not json",
        '{"@type": "Event", "name": "Trailing comma",}',
        "",
        "[" * 5000 + "]" * 5000,  # too deep for the json module
    ],
    ids=["broken", "trailing-comma", "empty", "too-deep"],
)
def test_invalid_jsonld_is_ignored(block: str) -> None:
    markup = (
        f'<html><head><script type="application/ld+json">{block}</script>'
        f'<script type="application/ld+json">{json.dumps(event())}</script>'
        f"</head><body>{FILLER}</body></html>"
    )

    assert values(parse(markup)) == {"title": "Test Hack"}


def test_non_event_types_give_no_structured_values() -> None:
    page = parse(jsonld_page({"@type": "Organization", "name": "Not An Event"}))

    assert page.structured == {}


def test_event_with_the_page_url_is_preferred() -> None:
    other = event(name="Related Hack", url="https://example.org/other")
    this = event(name="This Hack", url=PAGE_URL + "/")  # normalized comparison

    assert values(parse(jsonld_page([other, this])))["title"] == "This Hack"


def test_raw_newlines_in_jsonld_strings_are_accepted() -> None:
    markup = (
        '<html><head><script type="application/ld+json">'
        '{"@type": "Event", "name": "Line\nBreak Hack"}'
        f"</script></head><body>{FILLER}</body></html>"
    )

    assert values(parse(markup))["title"] == "Line Break Hack"


def test_sub_events_do_not_replace_the_event() -> None:
    document = {
        "@type": "WebPage",
        "about": event(subEvent=[{"@type": "Event", "name": "Opening Talk"}]),
    }

    assert values(parse(jsonld_page(document)))["title"] == "Test Hack"


# --- dates --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-11-14", date(2026, 11, 14)),
        ("2026-11-14T09:00", date(2026, 11, 14)),  # no offset: the date as written
        ("2026-11-14T23:30:00Z", date(2026, 11, 15)),  # 02:30 in Istanbul
        ("2026-11-14T23:30:00.000+00:00", date(2026, 11, 15)),
        ("2026-11-14T01:00:00-05:00", date(2026, 11, 14)),  # 09:00 in Istanbul
        ("2026-11-14T00:30:00+03:00", date(2026, 11, 14)),
        ("14.11.2026", None),
        ("2026-13-01", None),
        ("next Saturday", None),
    ],
)
def test_start_date(raw: str, expected: date | None) -> None:
    assert values(parse(jsonld_page(event(startDate=raw)))).get("start_date") == expected


def test_non_string_dates_are_ignored() -> None:
    assert "start_date" not in values(parse(jsonld_page(event(startDate=20261114))))


# --- format and location -----------------------------------------------------------


@pytest.mark.parametrize(
    ("properties", "expected"),
    [
        ({"eventAttendanceMode": "https://schema.org/OnlineEventAttendanceMode"}, "online"),
        ({"eventAttendanceMode": "OfflineEventAttendanceMode"}, "in_person"),
        ({"eventAttendanceMode": "schema:MixedEventAttendanceMode"}, "hybrid"),
        ({"location": {"@type": "VirtualLocation", "url": "https://meet.example.com"}}, "online"),
        ({"location": "Online"}, "online"),
        ({"location": "Çevrimiçi"}, "online"),
        (
            {"location": [{"@type": "VirtualLocation"}, {"@type": "Place", "name": "Hall A"}]},
            "hybrid",
        ),
        # The declared attendance mode wins over what the locations suggest.
        (
            {
                "eventAttendanceMode": "OfflineEventAttendanceMode",
                "location": {"@type": "VirtualLocation"},
            },
            "in_person",
        ),
        ({"location": {"@type": "Place", "name": "Hall A"}}, None),  # a place alone: unknown
        ({"eventAttendanceMode": "SomethingElse"}, None),
    ],
)
def test_format(properties: dict[str, Any], expected: str | None) -> None:
    assert values(parse(jsonld_page(event(**properties)))).get("format") == expected


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        (
            {
                "@type": "Place",
                "name": "Hall A",
                "address": {"addressLocality": "İstanbul", "addressCountry": "tr"},
            },
            {"venue": "Hall A", "city": "İstanbul", "country": "TR"},
        ),
        (
            {"@type": "PostalAddress", "addressLocality": "Berlin", "addressCountry": "Germany"},
            {"city": "Berlin"},  # country name without a known code: left out
        ),
        (
            {"@type": "Place", "name": "Hall A", "address": "1 Main St, Ankara"},
            {"venue": "Hall A"},  # free-text address: not split
        ),
        ({"@type": "Place", "address": {"addressCountry": {"name": "Turkey"}}}, {"country": "TR"}),
        ({"@type": "Place", "address": {"addressCountry": "TUR"}}, {}),  # alpha-3: not mapped
        ("Mühendislik Fakültesi, Elazığ", {"venue": "Mühendislik Fakültesi, Elazığ"}),
    ],
)
def test_location(location: Any, expected: dict[str, str]) -> None:
    found = values(parse(jsonld_page(event(location=location))))

    assert {key: found[key] for key in ("venue", "city", "country") if key in found} == expected


def test_venue_equal_to_the_event_name_is_dropped() -> None:
    location = {"@type": "Place", "name": "TEST hack", "address": {"addressLocality": "Ankara"}}

    found = values(parse(jsonld_page(event(location=location))))

    assert "venue" not in found
    assert found["city"] == "Ankara"


# --- offers, URLs, free ------------------------------------------------------------


@pytest.mark.parametrize(
    ("properties", "expected"),
    [
        ({"offers": {"price": 0}}, True),
        ({"offers": {"price": "0.00", "priceCurrency": "TRY"}}, True),
        ({"offers": [{"price": 250}, {"price": "0"}]}, True),
        ({"offers": {"price": 250}}, None),
        ({"offers": {"price": "Free"}}, None),
        ({"offers": {"price": True}}, None),
        ({"isAccessibleForFree": True}, True),
        ({"isAccessibleForFree": "True"}, True),
    ],
)
def test_is_free(properties: dict[str, Any], expected: bool | None) -> None:
    assert values(parse(jsonld_page(event(**properties)))).get("is_free") == expected


@pytest.mark.parametrize(
    ("properties", "expected"),
    [
        ({"offers": {"url": "https://apply.example.com/form"}}, "https://apply.example.com/form"),
        ({"offers": {"url": "/hack/register"}}, "https://example.org/hack/register"),
        ({"url": "https://register.example.net/x"}, "https://register.example.net/x"),
        ({"url": PAGE_URL}, None),  # the page itself
        ({"url": "https://www.example.org/hack/?utm_source=x"}, None),  # same, normalized
        ({"offers": {"url": "javascript:alert(1)"}}, None),
        ({"offers": {"url": "ftp://example.org/file"}}, None),
        ({"offers": {"url": "https://user:pw@example.org/"}}, None),
        (
            {"offers": {"url": "mailto:team@example.org"}, "url": "https://reg.example.com/"},
            "https://reg.example.com/",  # falls back to the event's own URL
        ),
    ],
)
def test_application_url(properties: dict[str, Any], expected: str | None) -> None:
    assert values(parse(jsonld_page(event(**properties)))).get("application_url") == expected


def test_application_url_equal_to_the_final_url_is_dropped() -> None:
    page = parse(
        jsonld_page(event(url="https://example.org/hack-2026")),
        url="https://example.org/h",
        final_url="https://example.org/hack-2026",
    )

    assert "application_url" not in page.structured


# --- text values and the event field rules -----------------------------------------


def test_values_failing_the_event_rules_are_dropped() -> None:
    page = parse(jsonld_page(event(name="ab", organizer={"name": "x" * 161})))

    assert page.structured == {}


def test_html_entities_and_whitespace_are_cleaned() -> None:
    page = parse(jsonld_page(event(name="  R&amp;D\n  Hack ", organizer=" Club  A ")))

    assert values(page) == {"title": "R&D Hack", "organizer": "Club A"}
    assert page.structured["title"].snippet == "R&amp;D\n  Hack"


def test_organizer_shapes() -> None:
    organizers = [{"@type": "Person"}, {"@type": "Person", "name": "Ayşe Yılmaz"}]

    assert values(parse(jsonld_page(event(organizer=organizers))))["organizer"] == "Ayşe Yılmaz"


def test_summary_rules() -> None:
    short = parse(jsonld_page(event(description="<p>Build <b>tools</b> for   farmers.</p>")))
    long = parse(jsonld_page(event(description="word " * 70)))  # 349 chars collapsed

    assert values(short)["summary"] == "Build tools for farmers."
    assert "summary" not in long.structured


def test_jsonld_summary_wins_over_meta() -> None:
    head = '<meta property="og:description" content="From meta.">'
    page = parse(jsonld_page(event(description="From JSON-LD."), head=head))

    assert page.structured["summary"] == StructuredValue(
        value="From JSON-LD.", source="jsonld", snippet="From JSON-LD."
    )


def test_meta_description_is_the_last_summary_fallback() -> None:
    head = '<meta name="description" content="Plain meta description.">'

    assert values(parse(jsonld_page(head=head))) == {"summary": "Plain meta description."}


def test_long_meta_description_is_not_a_summary() -> None:
    head = f'<meta property="og:description" content="{"word " * 70}">'

    assert parse(jsonld_page(head=head)).structured == {}


def test_snippets_are_capped() -> None:
    organizer = {"@type": "Organization", "name": "Club", "description": "x" * 500}

    snippet = parse(jsonld_page(event(organizer=organizer))).structured["organizer"].snippet

    assert len(snippet) == SNIPPET_MAX_CHARS
    assert snippet.startswith('{"@type": "Organization", "name": "Club"')


def test_maximum_attendee_capacity_is_ignored() -> None:
    page = parse(jsonld_page(event(maximumAttendeeCapacity=50)))

    assert values(page) == {"title": "Test Hack"}


@pytest.mark.parametrize(
    ("image", "expected"),
    [
        ("https://cdn.example.org/a.png", "https://cdn.example.org/a.png"),
        ("//cdn.example.org/a.png", "https://cdn.example.org/a.png"),
        ("data:image/png;base64,AAAA", None),
        ("javascript:alert(1)", None),
    ],
)
def test_og_image(image: str, expected: str | None) -> None:
    head = f'<meta property="og:image" content="{image}">'

    assert parse(jsonld_page(head=head)).image_url == expected


def test_title_falls_back_to_the_title_tag() -> None:
    page = parse(jsonld_page(head="<title>Hack &amp; Learn</title>"))

    assert page.title == "Hack & Learn"


def test_no_title_at_all() -> None:
    assert parse(jsonld_page()).title is None


# --- main text ----------------------------------------------------------------------


def test_long_text_is_truncated() -> None:
    paragraphs = "".join(f"<p>Paragraph {i}: {'lorem ipsum ' * 40}</p>" for i in range(100))

    page = parse(f"<html><body><article>{paragraphs}</article></body></html>")

    assert page.text_truncated
    assert len(page.text) == MAX_TEXT_CHARS


def test_plain_body_text_is_the_fallback() -> None:
    # A bare list of short lines: too little for trafilatura's article detection.
    lines = "".join(f"<div>Kural {i}: takımlar en fazla dört kişidir.</div>" for i in range(10))
    markup = f"<html><body><script>var x = 1;</script><style>p{{}}</style>{lines}</body></html>"

    page = parse(markup)

    assert "Kural 9: takımlar en fazla dört kişidir." in page.text
    assert "var x" not in page.text
    assert len(page.text) >= MIN_TEXT_CHARS


def test_short_page_has_no_readable_content() -> None:
    with pytest.raises(PageError, match="no readable content"):
        parse("<html><body><p>Too short.</p></body></html>")


# --- encodings ----------------------------------------------------------------------

TURKISH = "Çalıştay: İğne, şeker, ölçü, ünlü, ğ."
HTTP_EQUIV = '<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-9">'


@pytest.mark.parametrize(
    ("body", "declared"),
    [
        (TURKISH.encode("utf-8"), "utf-8"),
        (TURKISH.encode("utf-8"), None),  # undeclared UTF-8
        (b"\xef\xbb\xbf" + TURKISH.encode("utf-8"), "windows-1254"),  # the BOM wins
        (TURKISH.encode("cp1254"), "windows-1254"),
        (TURKISH.encode("cp1254"), "ISO-8859-9"),
        (TURKISH.encode("cp1254"), None),  # undeclared legacy page: cp1254
        (TURKISH.encode("cp1254"), "no-such-charset"),
        (f'<meta charset="windows-1254">{TURKISH}'.encode("cp1254"), None),
        (f"{HTTP_EQUIV}{TURKISH}".encode("cp1254"), None),
    ],
)
def test_decode_html(body: bytes, declared: str | None) -> None:
    assert decode_html(body, declared).endswith(TURKISH)


def test_http_charset_reaches_the_decoder() -> None:
    markup = jsonld_page(event(name="Doğu Hackathonu Şubat"))
    body = markup.encode("cp1254")

    page = loader(respond(body, "text/html; charset=windows-1254")).load_page(PAGE_URL)

    assert page.structured["title"].value == "Doğu Hackathonu Şubat"


# --- fetch errors -------------------------------------------------------------------


def test_blocked_url() -> None:
    with pytest.raises(PageError, match="URL not allowed: host resolves to a non-public"):
        loader(respond(b""), {"example.org": ["10.0.0.1"]}).load_page(PAGE_URL)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://127.0.0.1/", "ftp://example.org"])
def test_blocked_url_schemes_and_addresses(url: str) -> None:
    with pytest.raises(PageError, match="URL not allowed"):
        loader(respond(b"")).load_page(url)


@pytest.mark.parametrize("content_type", ["application/json", "image/png", "text/plain"])
def test_not_html(content_type: str) -> None:
    with pytest.raises(PageError, match="not an HTML page"):
        loader(respond(b"{}", content_type)).load_page(PAGE_URL)


def test_too_large() -> None:
    body = fixture("event_jsonld.html").encode("utf-8")

    with pytest.raises(PageError, match="too large"):
        loader(respond(body), max_body_bytes=1_000).load_page(PAGE_URL)


@pytest.mark.parametrize("status", [404, 410, 500, 503])
def test_http_error_status(status: int) -> None:
    body = fixture("event_jsonld.html").encode("utf-8")

    with pytest.raises(PageError, match=f"page returned HTTP {status}"):
        loader(respond(body, status=status)).load_page(PAGE_URL)


def test_timeout() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("slow")

    with pytest.raises(PageError, match="page could not be fetched: request timed out"):
        loader(handler).load_page(PAGE_URL)


def test_redirect_sets_the_final_url() -> None:
    body = fixture("event_jsonld.html").encode("utf-8")

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/h":
            return httpx2.Response(301, headers={"location": "/hack"})
        return respond(body)(request)

    page = loader(handler).load_page("https://example.org/h")

    assert page.requested_url == "https://example.org/h"
    assert page.final_url == PAGE_URL

"""Page loading for the URL import (V1.2 part A, docs/planning/V1_2_URL_IMPORT.md).

    SafeFetcher (HTML only) ─► decode (BOM, HTTP charset, <meta charset>, UTF-8, cp1254)
        ─► selectolax: JSON-LD schema.org/Event, OpenGraph/<meta> ─► structured values
        ─► trafilatura main text (Markdown), else the plain body text ─► PageContent

Structured values are deterministic and pass the event field rules (`EventUpdate`); a
value that does not is dropped here, so the extractor never sees it. The page is
untrusted input: nothing in it is executed or followed, and JSON-LD that does not parse
is ignored.
"""

import codecs
import html
import json
import re
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, cast
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import trafilatura
from pydantic import ValidationError
from selectolax.lexbor import LexborHTMLParser

from fhc_api.common.fields import check_http_url
from fhc_api.common.http import BlockedUrlError, ContentTypeError, FetchError, SafeFetcher
from fhc_api.common.normalize import fold_title, fold_turkish, normalize_url
from fhc_api.events.models import DEFAULT_TIMEZONE, EventFormat, EventUpdate
from fhc_api.importing.models import (
    MAX_TEXT_CHARS,
    ExtractableField,
    FieldValue,
    PageContent,
    PageError,
    StructuredValue,
)

HTML_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml"})
# Below this, the page is most likely an empty shell that renders in the browser.
MIN_TEXT_CHARS = 200
SNIPPET_MAX_CHARS = 300
SUMMARY_MAX_CHARS = 300  # events.summary
_MAX_JSONLD_DEPTH = 12  # nesting is walked this deep; deeper objects are ignored
_CHARSET_SNIFF_BYTES = 4096

# schema.org/Event and its subtypes (checked on schema.org 2026-10-11). `@type` may also
# be written as a full IRI or with a prefix (`https://schema.org/Event`, `schema:Event`).
EVENT_TYPES = frozenset(
    {
        "Event",
        "BusinessEvent",
        "ChildrensEvent",
        "ComedyEvent",
        "ConferenceEvent",
        "CourseInstance",
        "DanceEvent",
        "DeliveryEvent",
        "EducationEvent",
        "EventSeries",
        "ExhibitionEvent",
        "Festival",
        "FoodEvent",
        "Hackathon",
        "LiteraryEvent",
        "MusicEvent",
        "PerformingArtsEvent",
        "PublicationEvent",
        "BroadcastEvent",  # PublicationEvent subtypes
        "OnDemandEvent",
        "SaleEvent",
        "ScreeningEvent",
        "SocialEvent",
        "SportsEvent",
        "TheaterEvent",
        "VisualArtsEvent",
    }
)
_ATTENDANCE_MODES: dict[str, EventFormat] = {
    "OfflineEventAttendanceMode": "in_person",
    "OnlineEventAttendanceMode": "online",
    "MixedEventAttendanceMode": "hybrid",
}
# Folded country names that are common on Turkish pages; other names stay undetermined
# (no country table in V1.2). Two-letter codes are accepted as they are.
_COUNTRY_NAMES = {"turkiye": "TR", "turkey": "TR", "turkiye cumhuriyeti": "TR"}
_ONLINE_WORDS = frozenset({"online", "virtual", "cevrimici", "cevrim ici", "uzaktan"})
# WHATWG maps these labels to the Windows code pages (the bytes 0x80-0x9F differ).
_CHARSET_ALIASES = {
    "iso-8859-1": "cp1252",
    "latin1": "cp1252",
    "latin-1": "cp1252",
    "ascii": "cp1252",
    "us-ascii": "cp1252",
    "iso-8859-9": "cp1254",
    "latin5": "cp1254",
}
_BOMS = (
    (codecs.BOM_UTF8, "utf-8"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
)
_META_CHARSET_RE = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([a-zA-Z0-9_.:-]+)""", re.I)
_HTML_TAG_RE = re.compile(r"<[a-zA-Z/!][^>]*>")


def _utc_now() -> datetime:
    return datetime.now(UTC)


class HtmlPageLoader:
    """`PageLoader` for static HTML pages. JS-only pages fail with "no readable content"
    (no browser rendering in V1.2)."""

    def __init__(
        self, fetcher: SafeFetcher | None = None, *, now: Callable[[], datetime] = _utc_now
    ) -> None:
        self._fetcher = fetcher or SafeFetcher()
        self._now = now

    def load_page(self, url: str) -> PageContent:
        fetched_at = self._now()
        try:
            result = self._fetcher.fetch(url, content_types=HTML_CONTENT_TYPES)
        except BlockedUrlError as exc:
            raise PageError(f"URL not allowed: {exc}") from exc
        except ContentTypeError as exc:
            raise PageError(f"not an HTML page: {exc}") from exc
        except FetchError as exc:
            raise PageError(f"page could not be fetched: {exc}") from exc
        if not 200 <= result.status_code < 300:
            raise PageError(f"page returned HTTP {result.status_code}")
        return parse_page(
            decode_html(result.body, result.charset),
            requested_url=url,
            final_url=result.url,
            fetched_at=fetched_at,
        )


def parse_page(
    markup: str, *, requested_url: str, final_url: str, fetched_at: datetime
) -> PageContent:
    """Everything after the fetch; pure, so tests can call it with a fixture."""
    tree = LexborHTMLParser(markup)
    page_urls = {normalize_url(requested_url), normalize_url(final_url)}
    structured = _structured_from_jsonld(tree, page_urls, final_url)
    meta = _meta_tags(tree)
    if "summary" not in structured:
        for name in ("og:description", "description"):
            raw = meta.get(name)  # over 300 characters: fails the summary rule, skipped
            if value := _validated_value("summary", _collapse(raw), "meta", raw):
                structured["summary"] = value
                break
    text, truncated = _main_text(markup, final_url)
    return PageContent(
        requested_url=requested_url,
        final_url=final_url,
        fetched_at=fetched_at,
        title=_collapse(meta.get("og:title")) or _collapse(_title_tag(tree)),
        text=text,
        structured=structured,
        image_url=_absolute_http_url(meta.get("og:image"), final_url),
        text_truncated=truncated,
    )


# --- decoding -----------------------------------------------------------------------


def decode_html(body: bytes, declared: str | None) -> str:
    """BOM, then the HTTP charset, then <meta charset>, then UTF-8; cp1254 (Windows
    Turkish) is the last resort for undeclared legacy pages."""
    for bom, bom_encoding in _BOMS:
        if body.startswith(bom):
            return body[len(bom) :].decode(bom_encoding, errors="replace")
    sniffed = _META_CHARSET_RE.search(body[:_CHARSET_SNIFF_BYTES])
    for label in (declared, sniffed.group(1).decode("ascii") if sniffed else None):
        if encoding := _python_encoding(label):
            return body.decode(encoding, errors="replace")
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return body.decode("cp1254", errors="replace")


def _python_encoding(label: str | None) -> str | None:
    if not label:
        return None
    label = label.strip().lower()
    label = _CHARSET_ALIASES.get(label, label)
    try:
        return codecs.lookup(label).name
    except LookupError:
        return None


# --- JSON-LD ------------------------------------------------------------------------


def _structured_from_jsonld(
    tree: LexborHTMLParser, page_urls: set[str], base_url: str
) -> dict[ExtractableField, StructuredValue]:
    events = [node for document in _jsonld_documents(tree) for node in _event_nodes(document)]
    if not events:
        return {}
    # A page about one event may also list related ones: prefer the event whose own URL
    # is this page, else the first in document order.
    event = next((node for node in events if _same_page(node.get("url"), page_urls)), events[0])
    return _map_event(event, page_urls, base_url)


def _jsonld_documents(tree: LexborHTMLParser) -> Iterator[Any]:
    for script in tree.css("script[type]"):
        kind = (script.attributes.get("type") or "").split(";")[0].strip().lower()
        if kind != "application/ld+json":
            continue
        try:
            # strict=False: raw newlines inside strings are common in hand-written JSON-LD.
            yield json.loads(script.text(deep=True), strict=False)
        except (ValueError, RecursionError):  # invalid or absurdly deep: ignored
            continue


def _event_nodes(value: Any, depth: int = 0) -> Iterator[dict[str, Any]]:
    """Every Event object in document order: top level, arrays, `@graph`, nested."""
    if depth > _MAX_JSONLD_DEPTH:
        return
    if isinstance(value, list):
        for item in value:
            yield from _event_nodes(item, depth + 1)
    elif isinstance(value, dict):
        if _types(value) & EVENT_TYPES:
            yield value
        for key, item in value.items():
            if key != "subEvent":  # parts of the event, not the event itself
                yield from _event_nodes(item, depth + 1)


def _types(node: dict[str, Any]) -> set[str]:
    raw = node.get("@type")
    names = raw if isinstance(raw, list) else [raw]
    return {re.split(r"[/:#]", name)[-1] for name in names if isinstance(name, str)}


def _map_event(
    event: dict[str, Any], page_urls: set[str], base_url: str
) -> dict[ExtractableField, StructuredValue]:
    found: dict[ExtractableField, StructuredValue] = {}

    def put(field: ExtractableField, value: object, raw: object) -> None:
        if field not in found and (proposal := _validated_value(field, value, "jsonld", raw)):
            found[field] = proposal

    put("title", _clean_text(event.get("name")), event.get("name"))
    organizer = _first_name(event.get("organizer"))
    put("organizer", organizer, event.get("organizer"))
    put("summary", _short_summary(event.get("description")), event.get("description"))
    for field, key in (("start_date", "startDate"), ("end_date", "endDate")):
        put(cast(ExtractableField, field), _event_date(event.get(key)), event.get(key))
    mode = _attendance_mode(event.get("eventAttendanceMode"))
    put("format", mode, event.get("eventAttendanceMode"))  # before location: it wins
    _map_location(event.get("location"), put)
    _map_offers(event, put, page_urls, base_url)
    # Platforms (e.g. Devpost) fill `Place.name` with the event name: that is no venue.
    venue, title = found.get("venue"), found.get("title")
    if venue and title and fold_title(str(venue.value)) == fold_title(str(title.value)):
        del found["venue"]
    return found


type _Put = Callable[[ExtractableField, object, object], None]


def _map_location(raw: object, put: _Put) -> None:
    """`Place`/`PostalAddress` → venue, city, country; `VirtualLocation` → online; both →
    hybrid. A physical place alone does not imply in-person (online events list one too).
    """
    locations = raw if isinstance(raw, list) else [raw]
    physical = virtual = False
    for location in locations:
        if isinstance(location, str):
            text = _clean_text(location)
            if text and fold_turkish(text) in _ONLINE_WORDS:
                virtual = True
            elif text:
                physical = True
                put("venue", text, location)
            continue
        if not isinstance(location, dict):
            continue
        types = _types(location)
        if "VirtualLocation" in types:
            virtual = True
            continue
        address = location if "PostalAddress" in types else location.get("address")
        if address is None and not location.get("name"):
            continue
        physical = True
        if "PostalAddress" not in types:  # a Place (or one of its many subtypes)
            put("venue", _clean_text(location.get("name")), location.get("name"))
        if isinstance(address, dict):
            locality, country = address.get("addressLocality"), address.get("addressCountry")
            put("city", _clean_text(locality), locality)
            put("country", _country_code(country), country)
    if virtual:
        put("format", "hybrid" if physical else "online", raw)


def _map_offers(event: dict[str, Any], put: _Put, page_urls: set[str], base_url: str) -> None:
    raw = event.get("offers")
    offers = [
        offer for offer in (raw if isinstance(raw, list) else [raw]) if isinstance(offer, dict)
    ]
    mode_free = event.get("isAccessibleForFree")
    if mode_free is True or (isinstance(mode_free, str) and mode_free.lower() == "true"):
        put("is_free", True, mode_free)
    for offer in offers:
        if _decimal(offer.get("price")) == 0:
            put("is_free", True, offer)
    # Registration link: the offer's URL, else the event's own `url` when it points
    # elsewhere (the page itself is already the event's official URL).
    for candidate in [offer.get("url") for offer in offers] + [event.get("url")]:
        url = _absolute_http_url(candidate, base_url)
        if url and not _same_page(url, page_urls):
            put("application_url", url, candidate)


def _first_name(raw: object) -> str | None:
    """Organizer as text, an Organization/Person object, or a list of either."""
    for item in raw if isinstance(raw, list) else [raw]:
        name = _clean_text(item.get("name") if isinstance(item, dict) else item)
        if name:
            return name
    return None


def _short_summary(raw: object) -> str | None:
    text = _clean_text(raw)
    if text and _HTML_TAG_RE.search(text):
        text = _collapse(LexborHTMLParser(text).text(separator=" "))
    if not text or len(text) > SUMMARY_MAX_CHARS:
        return None  # a long description is not a summary; the LLM may shorten it
    return text


def _event_date(raw: object) -> date | None:
    """ISO 8601 date or date-time. With an offset, the calendar date in Europe/Istanbul
    (the date the event is listed under); without one, the date as written."""
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw.strip())
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(ZoneInfo(DEFAULT_TIMEZONE))
    return parsed.date()


def _attendance_mode(raw: object) -> EventFormat | None:
    if not isinstance(raw, str):
        return None
    return _ATTENDANCE_MODES.get(re.split(r"[/:#]", raw.strip())[-1])


def _country_code(raw: object) -> str | None:
    if isinstance(raw, dict):
        raw = raw.get("name") or raw.get("identifier")
    text = _clean_text(raw)
    if not text:
        return None
    if len(text) == 2:
        return text  # validated as ISO 3166-1 alpha-2 by CountryCode
    return _COUNTRY_NAMES.get(" ".join(fold_turkish(text).split()))


def _decimal(raw: object) -> Decimal | None:
    if isinstance(raw, bool) or not isinstance(raw, int | float | str):
        return None
    try:
        return Decimal(str(raw).strip())
    except InvalidOperation:
        return None


# --- meta tags ----------------------------------------------------------------------


def _meta_tags(tree: LexborHTMLParser) -> dict[str, str]:
    """`<meta property|name=... content=...>`, first occurrence wins, keys lower-case."""
    tags: dict[str, str] = {}
    for meta in tree.css("meta[content]"):
        key = meta.attributes.get("property") or meta.attributes.get("name")
        content = meta.attributes.get("content")
        if key and content and content.strip():
            tags.setdefault(key.strip().lower(), content)
    return tags


def _title_tag(tree: LexborHTMLParser) -> str | None:
    node = tree.css_first("title")
    return node.text(deep=True) if node is not None else None


# --- main text ----------------------------------------------------------------------


def _main_text(markup: str, url: str) -> tuple[str, bool]:
    text = (
        trafilatura.extract(
            markup,
            url=url,
            output_format="markdown",
            include_comments=False,
            include_tables=True,
            include_formatting=True,
            include_links=False,
            include_images=False,
            deduplicate=True,
        )
        or ""
    ).strip()
    if len(text) < MIN_TEXT_CHARS:
        fallback = _body_text(markup)
        text = fallback if len(fallback) > len(text) else text
    if len(text) < MIN_TEXT_CHARS:
        raise PageError(
            "no readable content: the page has almost no text without a browser; "
            "the page may need JavaScript"
        )
    if len(text) > MAX_TEXT_CHARS:
        return text[:MAX_TEXT_CHARS], True
    return text, False


def _body_text(markup: str) -> str:
    """Plain visible text of <body>, scripts and styles removed (trafilatura fallback).
    A fresh tree: the one used for JSON-LD and meta tags stays untouched."""
    tree = LexborHTMLParser(markup)
    tree.strip_tags(["script", "style", "noscript", "template", "svg"], recursive=True)
    raw = tree.body.text(separator="\n") if tree.body is not None else ""
    lines = (" ".join(line.split()) for line in raw.splitlines())
    return "\n".join(line for line in lines if line)


# --- values -------------------------------------------------------------------------


def _validated_value(
    field: ExtractableField, value: object, source: Literal["jsonld", "meta"], raw: object
) -> StructuredValue | None:
    """The value after the `EventUpdate` rules for `field`, or None if it fails them."""
    if value is None or value == "":
        return None
    try:
        model = EventUpdate.model_validate({field: value})
    except ValidationError:
        return None
    checked: FieldValue | None = getattr(model, field)
    if checked is None:
        return None
    return StructuredValue(value=checked, source=source, snippet=_snippet(raw))


def _snippet(raw: object) -> str:
    text = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
    text = text.strip()
    if len(text) <= SNIPPET_MAX_CHARS:
        return text
    return text[: SNIPPET_MAX_CHARS - 1] + "…"


def _clean_text(raw: object) -> str | None:
    """JSON-LD text with HTML entities decoded and whitespace collapsed."""
    if not isinstance(raw, str):
        return None
    return _collapse(html.unescape(raw))


def _collapse(text: str | None) -> str | None:
    collapsed = " ".join(text.split()) if text else ""
    return collapsed or None


def _absolute_http_url(raw: object, base_url: str) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None
    url = urljoin(base_url, raw.strip())
    try:
        return check_http_url(url)
    except ValueError:
        return None


def _same_page(raw: object, page_urls: set[str]) -> bool:
    return isinstance(raw, str) and normalize_url(raw) in page_urls

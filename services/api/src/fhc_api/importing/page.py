"""Page loading for the URL import (V1.2 part A, docs/planning/V1_2_URL_IMPORT.md).

    SafeFetcher (HTML only) ─► decode (BOM, HTTP charset, <meta charset>, UTF-8, cp1254)
        ─► selectolax: JSON-LD schema.org/Event, OpenGraph/<meta> ─► structured values
        ─► trafilatura main text (Markdown), then the page lines it left out (sidebars,
           info boxes; registration links with their target) ─► PageContent

Structured values are deterministic and pass the event field rules (`EventUpdate`); a
value that does not is dropped here, so the extractor never sees it. The page is
untrusted input: nothing in it is executed or followed, and JSON-LD that does not parse
is ignored.
"""

import codecs
import html
import json
import logging
import re
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, cast
from urllib.parse import urljoin, urlsplit
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

logger = logging.getLogger("fhc_api.importing")

HTML_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml"})
# Per-phase fetch timeout. Higher than the SafeFetcher default: on slow networks the TLS
# handshake alone took 5-10 s, and the admin waits for the import anyway.
FETCH_TIMEOUT_SECONDS = 20.0
# Below this, the page is most likely an empty shell that renders in the browser.
MIN_TEXT_CHARS = 200
SNIPPET_MAX_CHARS = 300
SUMMARY_MAX_CHARS = 300  # events.summary
_MAX_JSONLD_DEPTH = 12  # nesting is walked this deep; deeper objects are ignored
_CHARSET_SNIFF_BYTES = 4096

# schema.org/Event and its subtypes (checked on schema.org 2026-10-11). `@type` may also
# be written as a full IRI or with a prefix (`https://schema.org/Event`, `schema:Event`).
# "Hackathon" is not a schema.org type (see the design doc); some pages use it anyway,
# and accepting it is harmless.
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
# Charset labels accepted from the page or the HTTP header, a subset of the WHATWG
# Encoding Standard labels, mapped to Python codecs. A fixed list on purpose: Python's
# codec registry also has non-text codecs ("base64", "zlib", "rot13") and text codecs a
# page must not choose ("idna", "unicode_escape"). WHATWG maps the Latin-1 and Latin-5
# labels to the Windows code pages (the bytes 0x80-0x9F differ).
_ENCODING_LABELS: dict[str, str] = {
    **dict.fromkeys(("utf-8", "utf8", "unicode-1-1-utf-8"), "utf-8"),
    **dict.fromkeys(
        ("iso-8859-1", "iso8859-1", "latin1", "latin-1", "l1", "ascii", "us-ascii"), "cp1252"
    ),
    **dict.fromkeys(("iso-8859-9", "iso8859-9", "latin5", "l5"), "cp1254"),
    **{f"{prefix}{n}": f"cp{n}" for n in range(1250, 1259) for prefix in ("windows-", "cp")},
    **{
        f"{prefix}{n}": f"iso8859-{n}"
        for n in (2, 3, 4, 5, 6, 7, 8, 10, 13, 14, 15, 16)
        for prefix in ("iso-8859-", "iso8859-")
    },
    "windows-874": "cp874",
    "koi8-r": "koi8-r",
    "koi8-u": "koi8-u",
    "ibm866": "cp866",
    "macintosh": "mac-roman",
    "x-mac-cyrillic": "mac-cyrillic",
    "gbk": "gbk",
    "gb2312": "gbk",
    "gb18030": "gb18030",
    "big5": "big5",
    "euc-jp": "euc_jp",
    "iso-2022-jp": "iso2022_jp",
    "shift_jis": "shift_jis",
    "sjis": "shift_jis",
    "euc-kr": "euc_kr",
    "utf-16": "utf-16-le",
    "utf-16le": "utf-16-le",
    "utf-16be": "utf-16-be",
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
        self._fetcher = fetcher or SafeFetcher(timeout=FETCH_TIMEOUT_SECONDS)
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
        try:
            return parse_page(
                decode_html(result.body, result.charset),
                requested_url=url,
                final_url=result.url,
                fetched_at=fetched_at,
            )
        except PageError:
            raise
        except Exception as exc:
            # The page is untrusted: a parser bug must not become a 500. The type name
            # only, never page content, goes to the log.
            logger.warning("import: parsing the page failed (%s)", type(exc).__name__)
            raise PageError("page could not be parsed") from exc


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
            return _decode(body[len(bom) :], bom_encoding)
    if encoding := _python_encoding(declared):
        return _decode(body, encoding)
    sniffed = _META_CHARSET_RE.search(body[:_CHARSET_SNIFF_BYTES])
    label = sniffed.group(1).decode("ascii").strip().lower() if sniffed else ""
    if label.startswith(("utf-16", "utf-32")):
        # WHATWG: a <meta> that could be read as ASCII is not UTF-16/32; it means UTF-8.
        return _decode(body, "utf-8")
    if encoding := _python_encoding(label):
        return _decode(body, encoding)
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return body.decode("cp1254", errors="replace")


def _decode(body: bytes, encoding: str) -> str:
    try:
        return body.decode(encoding, errors="replace")
    except (LookupError, UnicodeError):  # not expected for the listed codecs; be safe
        return body.decode("utf-8", errors="replace")


def _python_encoding(label: str | None) -> str | None:
    return _ENCODING_LABELS.get(label.strip().lower()) if label else None


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
    if not _is_hosting_platform(event.get("organizer"), base_url):
        put("organizer", _first_name(event.get("organizer")), event.get("organizer"))
    put("summary", _short_summary(event.get("description")), event.get("description"))
    for field, key in (("start_date", "startDate"), ("end_date", "endDate")):
        put(cast(ExtractableField, field), _event_date(event.get(key)), event.get(key))
    mode = _attendance_mode(event.get("eventAttendanceMode"))
    put("format", mode, event.get("eventAttendanceMode"))  # before location: it wins
    _map_location(event.get("location"), put)
    _map_offers(event, put, page_urls, base_url)
    # Platforms (e.g. Devpost) fill `Place.name` with the event name: that is no venue.
    venue, title = found.get("venue"), found.get("title")
    # A `Place.name` that is only the city ("İstanbul") is no venue either.
    city = found.get("city")
    if venue and any(
        other and fold_title(str(venue.value)) == fold_title(str(other.value))
        for other in (title, city)
    ):
        del found["venue"]
    return found


def _is_hosting_platform(raw: object, base_url: str) -> bool:
    """True when the organizer is the platform the page is hosted on: its `url` is the
    site of a parent domain of the page host (an organizer "Devpost, Inc." with
    https://devpost.com/ on https://myhack.devpost.com/). The real organizer is then in the
    page text, for the LLM."""
    host = (urlsplit(base_url).hostname or "").lower().removeprefix("www.")
    for item in raw if isinstance(raw, list) else [raw]:
        url = item.get("url") if isinstance(item, dict) else None
        if not isinstance(url, str):
            continue
        parts = urlsplit(url.strip())
        organizer_host = (parts.hostname or "").lower().removeprefix("www.")
        if organizer_host and host.endswith(f".{organizer_host}") and parts.path in ("", "/"):
            return True
    return False


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
    # Free only when every priced offer is 0: "0" for students and "500" for others is
    # not a free event. No price at all says nothing.
    prices = [price for offer in offers if (price := _decimal(offer.get("price"))) is not None]
    if prices and all(price == 0 for price in prices):
        put("is_free", True, raw)
    # Registration link: an offer's URL, else a RegisterAction target. The event's own
    # `url` is not used: it is usually the event page, not the application form.
    for candidate in [offer.get("url") for offer in offers] + _register_targets(event):
        url = _absolute_http_url(candidate, base_url)
        if url and not _same_page(url, page_urls):
            put("application_url", url, candidate)


def _register_targets(event: dict[str, Any]) -> list[object]:
    """`potentialAction: {"@type": "RegisterAction", "target": url | EntryPoint}`."""
    raw = event.get("potentialAction")
    targets: list[object] = []
    for action in raw if isinstance(raw, list) else [raw]:
        if not isinstance(action, dict) or "RegisterAction" not in _types(action):
            continue
        target = action.get("target")
        for item in target if isinstance(target, list) else [target]:
            targets.append(item.get("urlTemplate") if isinstance(item, dict) else item)
    return targets


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
    """ISO 8601 date or date-time, as the calendar date the page lists. A local offset
    ("2026-10-10T18:30-04:00") is the event's own time zone: the date as written. UTC ("Z",
    "+00:00") is usually a server serialization: the date in Europe/Istanbul. Without an
    offset, the date as written."""
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw.strip())
        if parsed.utcoffset() == timedelta(0):
            parsed = parsed.astimezone(ZoneInfo(DEFAULT_TIMEZONE))
    except (ValueError, OverflowError):  # OverflowError: shifted past year 1 or 9999
        return None
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
    """A finite, non-negative price; NaN, sNaN, Infinity and negatives are no price."""
    if isinstance(raw, bool) or not isinstance(raw, int | float | str):
        return None
    try:
        value = Decimal(str(raw).strip())
    except InvalidOperation:
        return None
    return value if value.is_finite() and value >= 0 else None


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
    """The visible page text in page order when it fits in MAX_TEXT_CHARS; else the
    trafilatura article text first, then the page lines it left out, cut at the limit.

    Event pages keep key facts outside the article: sidebars ("Ödül Havuzu 200.000 TL",
    "Team required: 2 to 4 members"), info boxes, timelines whose dates sit in a <span> next
    to the step ("3 Ağustos – 7 Eylül" / "Başvuru formu"). trafilatura drops those parts,
    so the article alone misses them; in page order a date keeps its label."""
    page_text = _page_text(markup, url)
    if MIN_TEXT_CHARS <= len(page_text) <= MAX_TEXT_CHARS:
        return page_text, False
    main = _article_text(markup, url)
    page_lines = page_text.splitlines()
    main_lines = {_line_key(line) for line in main.splitlines()}
    main_key = _line_key(main)
    extra: list[str] = []
    seen: set[str] = set()
    for line in page_lines:
        key = _line_key(line)
        if not key or key in main_lines or key in seen:
            continue
        if len(key) >= _CONTAINED_LINE_CHARS and key in main_key:
            continue  # the article has it, wrapped or split differently
        if len(key) >= _REPEATED_LINE_CHARS:
            seen.add(key)  # menus and cards repeat; short labels ("Online") may recur
        extra.append(line)
    text = "\n\n".join(part for part in (main, "\n".join(extra)) if part)
    if len(text) < MIN_TEXT_CHARS:
        raise PageError(
            "no readable content: the page has almost no text without a browser; "
            "the page may need JavaScript"
        )
    if len(text) > MAX_TEXT_CHARS:
        return text[:MAX_TEXT_CHARS], True
    return text, False


# A page line at least this long that occurs inside the article text is a duplicate.
_CONTAINED_LINE_CHARS = 30
# Page lines at least this long are kept once; shorter ones (labels, values) every time.
_REPEATED_LINE_CHARS = 20
_LINE_MARKUP = str.maketrans(dict.fromkeys("*_#>|`", " "))


def _line_key(line: str) -> str:
    """Comparison form of a text line: Markdown markup and list markers removed, case and
    whitespace folded."""
    key = " ".join(line.translate(_LINE_MARKUP).split()).casefold()
    return key.removeprefix("- ").strip()


def _article_text(markup: str, url: str) -> str:
    return (
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


# Elements that start a new line in the page text. Table cells stay on their row's line
# ("1st Place | $500"), inline elements (span, a, strong) on their block's line.
_BLOCK_TAGS = (
    "address", "article", "aside", "blockquote", "br", "dd", "details", "dialog", "div",
    "dl", "dt", "fieldset", "figcaption", "figure", "form", "h1", "h2", "h3", "h4", "h5",
    "h6", "header", "hr", "li", "main", "ol", "p", "pre", "section", "summary", "table",
    "tr", "ul",
)  # fmt: skip
# Site chrome: menus and footers carry account links ("Sign up") and other pages' news.
# A <header> counts as chrome only when it holds a menu; a page hero stays.
_CHROME_SELECTORS = ("header:has(nav)", "nav", "[role=navigation]", "footer")
# Link texts (folded, word prefixes) and URL path words that mark a registration link.
_APPLY_WORDS = ("basvur", "kayit", "kaydol", "register", "registration", "apply", "rsvp")
_APPLY_PHRASES = ("sign up", "join hackathon", "join the hackathon", "join now")
_APPLY_PATH_RE = re.compile(
    r"(?:^|[/._=&?-])(?:apply|application|register|registration|signup|basvuru|basvur|kayit"
    r"|forms?)(?:$|[/._=&?-])"
)
# In a menu only a call to apply counts ("Apply Now", "Hemen Başvur", "Başvuru Formu"), not
# a menu entry about applications in general ("Başvuru Dokümanları", "Başvurular").
_MENU_APPLY_RE = re.compile(
    r"\b(?:apply|basvur|basvurun|basvuru (?:yap|formu|form))\b|\bbasvuruyu tamamla"
)
# Path segments of site account pages: "Kayıt ol" or "Sign up" for the site, not the event.
_ACCOUNT_PATH_RE = re.compile(
    r"(?:^|/)(?:kayitol|kayit-ol|uyeol|uye-ol|uyelik|signup|sign-up|sign_up|login|giris"
    r"|account|accounts|users?|auth)(?:$|/)"
)
_FOLDED_WORD_RE = re.compile(r"[a-z]+")
_MAX_LINK_CHARS = 500  # events.application_url


def _page_text(markup: str, url: str) -> str:
    """Visible text of <body>, one line per block element, without scripts, styles and site
    chrome. Registration links keep their target: "Hemen Başvur (https://…/apply)", so the
    application URL is on the page text the extractor checks evidence against. A fresh
    tree: the one used for JSON-LD and meta tags stays untouched."""
    tree = LexborHTMLParser(markup)
    tree.strip_tags(["script", "style", "noscript", "template", "svg"], recursive=True)
    if tree.body is None:
        return ""
    page_urls = {normalize_url(url)}
    # A menu's "Apply Now" / "Başvur" button is often the only application link: kept as a
    # line at the end. Other menu links are not.
    menu_links: list[str] = []
    for selector in _CHROME_SELECTORS:
        for node in tree.body.css(selector):
            for anchor in node.css("a[href]"):
                text = " ".join(anchor.text(deep=True).split())
                target = _registration_target(text, anchor.attributes.get("href"), url)
                folded = " ".join(_FOLDED_WORD_RE.findall(fold_turkish(text)))
                if target and not _same_page(target, page_urls) and _MENU_APPLY_RE.search(folded):
                    menu_links.append(f"{text} ({target})")
            node.decompose()
    for anchor in tree.body.css("a[href]"):
        target = _registration_target(anchor.text(deep=True), anchor.attributes.get("href"), url)
        if target and not _same_page(target, page_urls):
            anchor.insert_after(f" ({target}) ")
    for node in tree.body.css(",".join(_BLOCK_TAGS)):
        node.insert_before("\n")
        node.insert_after("\n")
    raw = tree.body.text(separator=" ")
    lines = [" ".join(line.split()) for line in raw.splitlines()]
    return "\n".join(line for line in lines + menu_links if line)


def _registration_target(text: str, href: str | None, base_url: str) -> str | None:
    """The absolute URL of a link that reads like a registration or application link; not
    a site account page."""
    target = _absolute_http_url(href, base_url)
    if target is None or len(target) > _MAX_LINK_CHARS:
        return None
    path = fold_turkish(urlsplit(target).path)
    if _ACCOUNT_PATH_RE.search(path):
        return None
    folded = " ".join(_FOLDED_WORD_RE.findall(fold_turkish(text)))
    if (
        any(word.startswith(_APPLY_WORDS) for word in folded.split())
        or any(phrase in folded for phrase in _APPLY_PHRASES)
        or _APPLY_PATH_RE.search(path) is not None
    ):
        return target
    return None


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

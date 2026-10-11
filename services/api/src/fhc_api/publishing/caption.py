"""The Telegram channel caption for an event (V1.1a). Deterministic, Turkish, no LLM.

The audience is public, so the copy follows the public site (`apps/web/src/lib/copy.ts`,
`format.ts`): Turkish labels and dates ("9–11 Ekim 2026"), "Yüz yüze, Elazığ" for the place.
The caption never mentions "days left" or the phase, so the same event data always gives
the same text (and the same `publishable_hash` means the same caption).

`parse_mode=HTML`: every dynamic value goes through `escape_html` / `html_link`. Telegram
counts the caption limit (0-1024) after entity parsing, i.e. on the visible text: tags
and link targets do not count, `&amp;` counts as one character. Lengths are measured in
UTF-16 code units (how Telegram measures entities), which is never less than the number
of characters, so the check is on the safe side.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from fhc_api.telegram.formatting import escape_html, html_link, is_safe_http_url

CAPTION_MAX = 1024
# Below this many characters a clipped summary is dropped rather than shown as a stub.
_MIN_SUMMARY = 40
# Fallback widths when even the caption without a summary is too long (a long venue,
# city and organizer together). Title 160 + these always fit.
_FALLBACK_ORGANIZER = 80
_FALLBACK_PLACE = 120
ELLIPSIS = "…"

MONTHS = (
    "Ocak",
    "Şubat",
    "Mart",
    "Nisan",
    "Mayıs",
    "Haziran",
    "Temmuz",
    "Ağustos",
    "Eylül",
    "Ekim",
    "Kasım",
    "Aralık",
)
FORMAT_LABELS = {"in_person": "Yüz yüze", "online": "Çevrim içi", "hybrid": "Hibrit"}
# The web uses Intl.DisplayNames("tr"); Python has no CLDR data, so the likely countries
# are listed and any other code is shown as is. Turkey is implied and never shown.
COUNTRY_NAMES = {
    "AZ": "Azerbaycan",
    "DE": "Almanya",
    "FR": "Fransa",
    "GB": "Birleşik Krallık",
    "NL": "Hollanda",
    "US": "Amerika Birleşik Devletleri",
}
DATES_TBA = "Tarih açıklanacak"
NOT_SPECIFIED = "Belirtilmedi"

_TAG_RE = re.compile(r"<[^>]*>")
_ENTITIES = (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&amp;", "&"))


@dataclass(frozen=True)
class Caption:
    html: str  # what is sent with parse_mode=HTML
    text: str  # what readers see (tags removed, entities decoded)
    length: int  # of `text`, in UTF-16 code units
    truncated: bool  # the summary (or a long field) was shortened to fit


# --- formatting ----------------------------------------------------------------------


def telegram_length(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def visible_text(html: str) -> str:
    """The caption as Telegram shows it. Only valid for our own templates (no `<` or `>`
    outside tags, because every value is escaped)."""
    text = _TAG_RE.sub("", html)
    for entity, char in _ENTITIES:
        text = text.replace(entity, char)
    return text


def format_date(value: date) -> str:
    """Like "9 Ekim 2026"."""
    return f"{value.day} {MONTHS[value.month - 1]} {value.year}"


def format_date_range(start: date | None, end: date | None) -> str:
    """ "9 Ekim 2026", "9–11 Ekim 2026", "30 Ekim – 2 Kasım 2026", "30 Aralık 2026 – 2 Ocak
    2027" or "Tarih açıklanacak" (same rules as the public site)."""
    if start is None:
        return format_date(end) if end else DATES_TBA
    if end is None or end == start:
        return format_date(start)
    if (start.year, start.month) == (end.year, end.month):
        return f"{start.day}–{format_date(end)}"
    if start.year == end.year:
        return f"{start.day} {MONTHS[start.month - 1]} – {format_date(end)}"
    return f"{format_date(start)} – {format_date(end)}"


def _clean(value: object) -> str:
    return " ".join(str(value).split()) if value else ""


def format_place(event: Mapping[str, Any]) -> str:
    """ "Çevrim içi", "Hibrit, İstanbul", "Yüz yüze, Borsa İstanbul, İstanbul"."""
    event_format = event.get("format")
    if event_format == "online":
        return FORMAT_LABELS["online"]
    country = event.get("country")
    country_name = COUNTRY_NAMES.get(country, country) if country and country != "TR" else None
    parts: list[str] = []
    for part in (_clean(event.get("venue")), _clean(event.get("city")), _clean(country_name)):
        if part and part not in parts:
            parts.append(part)
    label = FORMAT_LABELS.get(event_format or "")
    if not parts:
        return label or NOT_SPECIFIED
    return ", ".join([label, *parts] if label else parts)


def format_team(team_min: int | None, team_max: int | None) -> str | None:
    if team_min is None and team_max is None:
        return None
    if team_max == 1:
        return "Bireysel"
    if team_min is None:
        return f"en fazla {team_max} kişi"
    if team_max is None:
        return f"en az {team_min} kişi"
    if team_min == team_max:
        return f"{team_max} kişi"
    return f"{team_min}–{team_max} kişi"


def clip(text: str, limit: int) -> str:
    """At most `limit` UTF-16 units; cut at a word boundary when one is near, then "…"."""
    if telegram_length(text) <= limit:
        return text
    budget = limit - telegram_length(ELLIPSIS)
    out: list[str] = []
    used = 0
    for char in text:
        size = telegram_length(char)
        if used + size > budget:
            break
        out.append(char)
        used += size
    cut = "".join(out)
    space = cut.rfind(" ")
    if space >= len(cut) - 30 and space > 0:
        cut = cut[:space]
    return cut.rstrip(" ,.;:–-") + ELLIPSIS


# --- caption ---------------------------------------------------------------------------


def _links(event: Mapping[str, Any], detail_url: str | None) -> str:
    links: list[str] = []
    official = event.get("official_url") or ""
    application = event.get("application_url") or ""
    for url, label in (
        (detail_url or "", "Ayrıntılar"),
        (official, "Resmî sayfa"),
        (application if application != official else "", "Başvuru"),
    ):
        if is_safe_http_url(url):
            links.append(html_link(url, label))
    return "🔗 " + " · ".join(links) if links else ""


def _render(
    event: Mapping[str, Any],
    detail_url: str | None,
    *,
    summary: str,
    organizer_max: int | None = None,
    place_max: int | None = None,
) -> str:
    title = _clean(event.get("title"))
    organizer = _clean(event.get("organizer"))
    place = format_place(event)
    if organizer_max is not None:
        organizer = clip(organizer, organizer_max)
    if place_max is not None:
        place = clip(place, place_max)

    head = [f"<b>{escape_html(title)}</b>"]
    if organizer:
        head.append(escape_html(organizer))
    dates = format_date_range(event.get("start_date"), event.get("end_date"))
    facts = [f"📅 Tarih: {escape_html(dates)}"]
    deadline = event.get("application_deadline")
    if deadline:
        facts.append(f"⏳ Son başvuru: {escape_html(format_date(deadline))}")
    facts.append(f"📍 Konum: {escape_html(place)}")
    team = format_team(event.get("team_min"), event.get("team_max"))
    if team:
        facts.append(f"👥 Takım: {escape_html(team)}")

    blocks = ["\n".join(head), "\n".join(facts)]
    if summary:
        blocks.append(escape_html(summary))
    links = _links(event, detail_url)
    if links:
        blocks.append(links)
    return "\n\n".join(blocks)


def _caption(html: str, truncated: bool) -> Caption:
    text = visible_text(html)
    return Caption(html=html, text=text, length=telegram_length(text), truncated=truncated)


def build_caption(event: Mapping[str, Any], *, detail_url: str | None) -> Caption:
    """`detail_url`: the public detail page (`WEB_BASE_URL/hackathonlar/<slug>`), or None
    when WEB_BASE_URL is not set (preview only; sending requires it)."""
    summary = _clean(event.get("summary"))
    full = _caption(_render(event, detail_url, summary=summary), truncated=False)
    if full.length <= CAPTION_MAX:
        return full

    without = _caption(_render(event, detail_url, summary=""), truncated=True)
    budget = CAPTION_MAX - without.length - telegram_length("\n\n")
    if summary and budget >= _MIN_SUMMARY:
        clipped = _caption(_render(event, detail_url, summary=clip(summary, budget)), True)
        if clipped.length <= CAPTION_MAX:
            return clipped
    if without.length <= CAPTION_MAX:
        return without

    narrow = _caption(
        _render(
            event,
            detail_url,
            summary="",
            organizer_max=_FALLBACK_ORGANIZER,
            place_max=_FALLBACK_PLACE,
        ),
        truncated=True,
    )
    if narrow.length > CAPTION_MAX:  # pragma: no cover - bounded by the column limits
        raise ValueError("caption does not fit into 1024 characters")
    return narrow

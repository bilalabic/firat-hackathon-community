"""Channel caption (V1.1a): Turkish formatting, escaping, length limit, missing fields."""

from datetime import date
from typing import Any

import pytest

from fhc_api.publishing.caption import (
    CAPTION_MAX,
    build_caption,
    clip,
    format_date,
    format_date_range,
    format_place,
    format_team,
    telegram_length,
    visible_text,
)

DETAIL = "https://fhc.example.org/hackathonlar/firat-hackathon"
EVENT: dict[str, Any] = {
    "slug": "firat-hackathon",
    "title": "Fırat Hackathon",
    "organizer": "Fırat Üniversitesi",
    "summary": "48 saatlik yapay zekâ hackathonu.",
    "start_date": date(2026, 10, 9),
    "end_date": date(2026, 10, 11),
    "application_deadline": date(2026, 10, 1),
    "format": "in_person",
    "venue": None,
    "city": "Elazığ",
    "country": "TR",
    "team_min": 2,
    "team_max": 5,
    "official_url": "https://example.com/hackathon",
    "application_url": "https://example.com/apply",
}


def test_full_caption() -> None:
    caption = build_caption(EVENT, detail_url=DETAIL)
    assert caption.html == (
        "<b>Fırat Hackathon</b>\n"
        "Fırat Üniversitesi\n"
        "\n"
        "📅 Tarih: 9–11 Ekim 2026\n"
        "⏳ Son başvuru: 1 Ekim 2026\n"
        "📍 Konum: Yüz yüze, Elazığ\n"
        "👥 Takım: 2–5 kişi\n"
        "\n"
        "48 saatlik yapay zekâ hackathonu.\n"
        "\n"
        f'🔗 <a href="{DETAIL}">Ayrıntılar</a> · '
        '<a href="https://example.com/hackathon">Resmî sayfa</a> · '
        '<a href="https://example.com/apply">Başvuru</a>'
    )
    assert caption.text.startswith("Fırat Hackathon\nFırat Üniversitesi\n")
    assert caption.text.endswith("🔗 Ayrıntılar · Resmî sayfa · Başvuru")
    assert caption.length == telegram_length(caption.text)
    assert not caption.truncated


def test_caption_is_deterministic() -> None:
    assert build_caption(EVENT, detail_url=DETAIL) == build_caption(dict(EVENT), detail_url=DETAIL)


def test_escaping_of_every_dynamic_value() -> None:
    event = {
        **EVENT,
        "title": "AI <Hack> & Co",
        "organizer": "R&D <Lab>",
        "summary": "Use <b>bold</b> & win",
        "city": "A&B",
        "official_url": 'https://example.com/?a=1&b="x"',
        "application_url": None,
    }
    caption = build_caption(event, detail_url=DETAIL)
    assert "<b>AI &lt;Hack&gt; &amp; Co</b>" in caption.html
    assert "R&amp;D &lt;Lab&gt;" in caption.html
    assert "Use &lt;b&gt;bold&lt;/b&gt; &amp; win" in caption.html
    assert "Yüz yüze, A&amp;B" in caption.html
    assert 'href="https://example.com/?a=1&amp;b=&quot;x&quot;"' in caption.html
    # Readers see the original characters.
    assert "AI <Hack> & Co" in caption.text
    assert "Use <b>bold</b> & win" in caption.text


def test_missing_fields() -> None:
    event = {
        "slug": "x",
        "title": "Minimal",
        "official_url": "https://example.com",
        "start_date": None,
        "format": None,
    }
    caption = build_caption(event, detail_url=None)
    assert caption.html == (
        "<b>Minimal</b>\n\n"
        "📅 Tarih: Tarih açıklanacak\n"
        "📍 Konum: Belirtilmedi\n\n"
        '🔗 <a href="https://example.com">Resmî sayfa</a>'
    )


def test_unsafe_urls_are_not_linked() -> None:
    event = {**EVENT, "official_url": "javascript:alert(1)", "application_url": "ftp://x"}
    caption = build_caption(event, detail_url=None)
    assert "javascript" not in caption.html
    assert "ftp" not in caption.html
    assert "🔗" not in caption.html


def test_application_link_is_omitted_when_it_equals_the_official_url() -> None:
    event = {**EVENT, "application_url": EVENT["official_url"]}
    assert "Başvuru</a>" not in build_caption(event, detail_url=DETAIL).html


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (date(2026, 10, 9), None, "9 Ekim 2026"),
        (date(2026, 10, 9), date(2026, 10, 9), "9 Ekim 2026"),
        (date(2026, 10, 9), date(2026, 10, 11), "9–11 Ekim 2026"),
        (date(2026, 10, 30), date(2026, 11, 2), "30 Ekim – 2 Kasım 2026"),
        (date(2026, 12, 30), date(2027, 1, 2), "30 Aralık 2026 – 2 Ocak 2027"),
        (None, date(2026, 2, 1), "1 Şubat 2026"),
        (None, None, "Tarih açıklanacak"),
    ],
)
def test_turkish_date_ranges(start: date | None, end: date | None, expected: str) -> None:
    assert format_date_range(start, end) == expected


def test_turkish_month_names() -> None:
    names = [format_date(date(2026, month, 1)).split()[1] for month in range(1, 13)]
    assert names == [
        "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
        "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
    ]  # fmt: skip


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"format": "online", "city": "İstanbul"}, "Çevrim içi"),
        ({"format": "hybrid", "city": "İstanbul"}, "Hibrit, İstanbul"),
        ({"format": "in_person", "venue": "Borsa İstanbul", "city": "İstanbul"},
         "Yüz yüze, Borsa İstanbul, İstanbul"),
        ({"format": "in_person", "city": "Berlin", "country": "DE"}, "Yüz yüze, Berlin, Almanya"),
        ({"format": "in_person", "city": "Elazığ", "country": "TR"}, "Yüz yüze, Elazığ"),
        ({"format": None, "city": "Paris", "country": "FR"}, "Paris, Fransa"),
        ({"format": "in_person", "country": "JP"}, "Yüz yüze, JP"),
        ({"format": "in_person"}, "Yüz yüze"),
        ({"format": None}, "Belirtilmedi"),
        ({"format": "hybrid", "venue": "Elazığ", "city": "Elazığ"}, "Hibrit, Elazığ"),
    ],
)  # fmt: skip
def test_place(fields: dict[str, Any], expected: str) -> None:
    assert format_place(fields) == expected


@pytest.mark.parametrize(
    ("team_min", "team_max", "expected"),
    [
        (None, None, None),
        (2, 5, "2–5 kişi"),
        (3, 3, "3 kişi"),
        (1, 1, "Bireysel"),
        (None, 4, "en fazla 4 kişi"),
        (2, None, "en az 2 kişi"),
    ],
)
def test_team(team_min: int | None, team_max: int | None, expected: str | None) -> None:
    assert format_team(team_min, team_max) == expected


def test_team_line_is_omitted_when_unknown() -> None:
    event = {**EVENT, "team_min": None, "team_max": None}
    assert "Takım" not in build_caption(event, detail_url=DETAIL).html


def test_clip_cuts_at_a_word_and_counts_utf16() -> None:
    assert clip("short", 10) == "short"
    clipped = clip("alpha beta gamma delta", 15)
    assert clipped == "alpha beta…"
    assert telegram_length(clip("😀" * 10, 7)) <= 7  # each emoji is 2 UTF-16 units
    assert telegram_length("😀") == 2


def test_visible_text_decodes_entities_once() -> None:
    assert visible_text('<b>a &amp;lt; b</b> <a href="x&quot;">l</a>') == "a &lt; b l"


def _longest_event() -> dict[str, Any]:
    """Every caption field at its database maximum."""
    return {
        **EVENT,
        "title": "T" * 160,
        "organizer": "O" * 160,
        "summary": " ".join(["kelime"] * 43)[:300],
        "venue": "V" * 200,
        "city": "C" * 120,
        "country": "JP",
        "start_date": date(2026, 12, 30),
        "end_date": date(2027, 1, 2),
        "official_url": "https://example.com/" + "o" * 470,
        "application_url": "https://example.com/" + "a" * 470,
    }


def test_long_event_fits_by_shortening_the_summary() -> None:
    event = {**_longest_event(), "venue": "V" * 140}
    caption = build_caption(event, detail_url=DETAIL)
    assert caption.truncated
    assert caption.length <= CAPTION_MAX
    assert "…" in caption.text
    assert "kelime" in caption.text
    # Links are entity data and do not count against the limit.
    assert caption.html.count("<a href=") == 3
    assert len(caption.html) <= 4096  # publications.body


def test_longest_event_still_fits() -> None:
    caption = build_caption(_longest_event(), detail_url=DETAIL)
    assert caption.truncated
    assert caption.length <= CAPTION_MAX
    assert "T" * 160 in caption.text  # the title is never shortened
    assert caption.html.count("<a href=") == 3
    assert len(caption.html) <= 4096


def test_oversized_fields_beyond_the_column_limits_are_clipped() -> None:
    # Not possible with today's column limits; the builder must still never exceed 1024.
    event = {**_longest_event(), "organizer": "O" * 900, "venue": "V" * 900}
    caption = build_caption(event, detail_url=DETAIL)
    assert caption.truncated
    assert caption.length <= CAPTION_MAX
    assert "kelime" not in caption.text  # the summary is dropped first
    assert "O" * 79 + "…" in caption.text


def test_emoji_heavy_text_is_measured_in_utf16() -> None:
    event = {**_longest_event(), "summary": "🚀" * 150, "venue": "V" * 140}
    caption = build_caption(event, detail_url=DETAIL)
    assert caption.length <= CAPTION_MAX
    assert telegram_length(caption.text) == caption.length

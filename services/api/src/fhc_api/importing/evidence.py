"""Deterministic evidence checks for LLM-proposed fields (AI_ARCHITECTURE §3).

The LLM must quote a snippet for every value. Code then checks, conservatively, that

1. the snippet occurs in the page text (`match_key` on both sides), and
2. the value is plausibly stated by the snippet: text values occur in it, the day and month
   of a date are written in it, a team size or prize amount appears as a number.

When the snippet carries no year, the year of a date comes from the fetch date
(`resolve_year`), not from the model.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from fhc_api.common.normalize import fold_turkish

# Quotes (curly, low-9, reversed, primes, grave, acute, guillemets) and dashes (hyphens,
# en/em dash, minus sign) that pages and models write interchangeably; Turkish i-forms fold
# to "i" before casefold ("İ".lower() would leave a combining dot, "I" is "ı" in Turkish).
_SINGLE_QUOTES = "\u2018\u2019\u201a\u201b\u2032`\u00b4"
_DOUBLE_QUOTES = "\u201c\u201d\u201e\u201f\u2033\u00ab\u00bb"
_DASHES = "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"
_MATCH_TRANSLATION = str.maketrans(
    {
        **dict.fromkeys(_SINGLE_QUOTES, "'"),
        **dict.fromkeys(_DOUBLE_QUOTES, '"'),
        **dict.fromkeys(_DASHES, "-"),
        "\u0130": "i", "I": "i", "\u0131": "i", "\u0307": None,  # İ, I, ı, combining dot
        # Markdown markup in the trafilatura text that a model leaves out when it quotes.
        "*": None, "_": None, "#": None, ">": None, "|": None, "\\": None,
    }
)  # fmt: skip
_WHITESPACE_RE = re.compile(r"\s+")
_SNIPPET_EDGE = " .,;:!?-'\"()[]"


def match_key(text: str) -> str:
    """Comparison form for evidence matching: NFKC, quotes/dashes unified, Turkish-aware
    casefold, Markdown emphasis removed, whitespace collapsed."""
    text = unicodedata.normalize("NFKC", text).translate(_MATCH_TRANSLATION).casefold()
    return _WHITESPACE_RE.sub(" ", text).strip()


def snippet_key(snippet: str) -> str:
    """`match_key` without the punctuation a model adds or drops at the ends of a quote."""
    return match_key(snippet).strip(_SNIPPET_EDGE)


def occurs_in(needle: str, haystack_key: str) -> bool:
    """True when `needle` (raw) occurs in `haystack_key` (already a `match_key`)."""
    key = snippet_key(needle)
    return bool(key) and key in haystack_key


# -- dates -----------------------------------------------------------------------------------

# Full month names (Turkish folded to ASCII, English) match as a word prefix, so suffixes such
# as "Ekim'e", "Ekimde" or "Aralığa" (k→ğ: "aralig") are covered. Abbreviations and the
# English "may" (also a verb, and "maybe" must not count) match exactly.
_MONTH_PREFIXES: tuple[tuple[str, int], ...] = (
    ("ocak", 1), ("subat", 2), ("mart", 3), ("nisan", 4), ("mayis", 5), ("haziran", 6),
    ("temmuz", 7), ("agustos", 8), ("eylul", 9), ("ekim", 10), ("kasim", 11),
    ("aralik", 12), ("aralig", 12),
    ("january", 1), ("february", 2), ("march", 3), ("april", 4), ("june", 6),
    ("july", 7), ("august", 8), ("september", 9), ("october", 10), ("november", 11),
    ("december", 12),
)  # fmt: skip
_MONTH_ABBREVIATIONS = {
    "oca": 1, "sub": 2, "mar": 3, "nis": 4, "haz": 6, "tem": 7, "agu": 8, "eyl": 9,
    "eki": 10, "kas": 11, "ara": 12,
    "jan": 1, "feb": 2, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9,
    "oct": 10, "nov": 11, "dec": 12,
}  # fmt: skip
_WORD_RE = re.compile(r"[a-z]+")
_NUMBER_RE = re.compile(r"\d+")
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_DMY_DATE_RE = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4}|\d{2})\b")

# A date without a year stays in the fetch year unless that puts it more than this far
# before the fetch date; then it is next year ("10 Ocak" fetched in October → next January).
YEAR_LOOKBACK = timedelta(days=90)


def months_named(text: str) -> set[int]:
    months: set[int] = set()
    for word in _WORD_RE.findall(fold_turkish(text)):
        if word in _MONTH_ABBREVIATIONS:
            months.add(_MONTH_ABBREVIATIONS[word])
            continue
        months.update(month for prefix, month in _MONTH_PREFIXES if word.startswith(prefix))
    return months


def resolve_year(month: int, day: int, fetch_date: date) -> date | None:
    """The date for `day.month.` without a year, read on `fetch_date` (see YEAR_LOOKBACK).
    None when the day does not exist in the chosen year (29 February)."""
    try:
        candidate = date(fetch_date.year, month, day)
        if candidate < fetch_date - YEAR_LOOKBACK:
            candidate = date(fetch_date.year + 1, month, day)
    except ValueError:
        return None
    return candidate


@dataclass(frozen=True)
class DateEvidence:
    value: date | None  # None: the snippet does not support the date
    year_inferred: bool = False
    reason: str = ""


def check_date(value: date, snippet: str, fetch_date: date) -> DateEvidence:
    """Check that the snippet states `value`'s day and month; take the year from the snippet
    when it has one, else from `resolve_year` (the model's year is then ignored)."""
    text = match_key(snippet)
    numeric = [(int(d), int(m), int(y)) for y, m, d in _ISO_DATE_RE.findall(text)] + [
        (int(d), int(m), int(y) + 2000 if len(y) == 2 else int(y))
        for d, m, y in _DMY_DATE_RE.findall(text)
    ]
    numbers = {int(n) for n in _NUMBER_RE.findall(text)}
    years = {n for n in numbers if 1900 <= n <= 2100} | {y for _, _, y in numeric}
    months = months_named(snippet)

    if months:
        if value.month not in months or value.day not in numbers:
            return DateEvidence(None, reason="day and month are not both in the snippet")
    elif not any((d, m) == (value.day, value.month) for d, m, _ in numeric):
        return DateEvidence(None, reason="the snippet has no matching day and month")

    if years:
        if value.year not in years:
            return DateEvidence(None, reason="the year is not in the snippet")
        return DateEvidence(value)
    resolved = resolve_year(value.month, value.day, fetch_date)
    if resolved is None:
        return DateEvidence(None, reason="the day does not exist in the inferred year")
    return DateEvidence(resolved, year_inferred=True)


# -- numbers ---------------------------------------------------------------------------------

_NUMBER_WORDS = {
    "tek": 1, "bireysel": 1, "solo": 1, "single": 1, "individual": 1, "individually": 1,
    "iki": 2, "two": 2, "uc": 3, "three": 3, "dort": 4, "four": 4, "bes": 5, "five": 5,
    "alti": 6, "six": 6, "yedi": 7, "seven": 7, "sekiz": 8, "eight": 8, "dokuz": 9,
    "nine": 9, "ten": 10,
}  # fmt: skip


def mentions_count(value: int, snippet: str) -> bool:
    """True when `value` appears in the snippet as a number or a number word (1-10)."""
    folded = fold_turkish(snippet)
    if value in {int(n) for n in _NUMBER_RE.findall(folded)}:
        return True
    return any(_NUMBER_WORDS.get(word) == value for word in _WORD_RE.findall(folded))


_AMOUNT_RE = re.compile(
    r"(?<![\d.,])(\d+(?:[.,]\d+)*)(?!\d)(?:\s*(bin|thousand|milyon|million|mn|k|m)(?![a-z]))?"
)
_MULTIPLIERS = {
    "bin": 1000, "thousand": 1000, "k": 1000,
    "milyon": 1_000_000, "million": 1_000_000, "mn": 1_000_000, "m": 1_000_000,
}  # fmt: skip


def _parse_number(token: str) -> set[Decimal]:
    """Readings of "50.000", "50,000", "1,5", "1.234,56": a separator followed by exactly
    three digits is a thousands separator; otherwise the last separator is the decimal one."""
    groups = re.split(r"[.,]", token)
    readings: set[Decimal] = set()
    if len(groups) > 1 and all(len(group) == 3 for group in groups[1:]):
        readings.add(Decimal("".join(groups)))
    if len(groups) > 1:
        readings.add(Decimal(f"{''.join(groups[:-1])}.{groups[-1]}"))
    else:
        readings.add(Decimal(token))
    return readings


def mentions_amount(value: Decimal, snippet: str) -> bool:
    """True when the snippet writes `value` as an amount ("50.000 TL", "$10K", "1,5 milyon")."""
    for token, suffix in _AMOUNT_RE.findall(fold_turkish(snippet)):
        multiplier = _MULTIPLIERS.get(suffix, 1)
        if any(reading * multiplier == value for reading in _parse_number(token)):
            return True
    return False

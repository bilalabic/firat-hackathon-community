"""Deterministic evidence checks for LLM-proposed fields (AI_ARCHITECTURE §3).

The LLM must quote a snippet for every value. Code then checks, conservatively, that

1. the snippet is long enough to be evidence, does not read like an instruction to the
   model, and occurs in the page text (`match_key` on both sides), and
2. the value is plausibly stated by the snippet: text values occur in it as whole words, the
   day of a date is written next to its month, a team size or prize amount appears as a
   number, a format, fee, currency or country is named by a keyword. URLs must be on the page.

When the snippet carries no year, the year of a date comes from the fetch date
(`resolve_year`), not from the model.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from fhc_api.common.normalize import fold_turkish, normalize_url

# Quotes (curly, low-9, reversed, primes, grave, acute, guillemets) and dashes (hyphens,
# en/em dash, minus sign) that pages and models write interchangeably; Turkish i-forms fold
# to "i" before casefold ("İ".lower() would leave a combining dot, "I" is "ı" in Turkish).
_SINGLE_QUOTES = "".join(map(chr, (0x2018, 0x2019, 0x201A, 0x201B, 0x2032, 0x60, 0xB4)))
_DOUBLE_QUOTES = "".join(map(chr, (0x201C, 0x201D, 0x201E, 0x201F, 0x2033, 0xAB, 0xBB)))
_DASHES = "".join(map(chr, (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212)))
_MATCH_TRANSLATION = str.maketrans(
    {
        **dict.fromkeys(_SINGLE_QUOTES, "'"),
        **dict.fromkeys(_DOUBLE_QUOTES, '"'),
        **dict.fromkeys(_DASHES, "-"),
        "İ": "i", "I": "i", "ı": "i", chr(0x307): None,  # combining dot above
        # Markdown markup in the trafilatura text that a model leaves out when it quotes.
        "*": None, "_": None, "#": None, ">": None, "|": None, "\\": None,
    }
)  # fmt: skip
_WHITESPACE_RE = re.compile(r"\s+")
_SNIPPET_EDGE = " .,;:!?-'\"()[]"

# A snippet shorter than this (after normalization) proves nothing: "a" occurs on every page.
MIN_SNIPPET_CHARS = 12
MIN_SNIPPET_WORDS = 2


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


def long_enough(snippet: str) -> bool:
    key = snippet_key(snippet)
    return len(key) >= MIN_SNIPPET_CHARS or len(key.split()) >= MIN_SNIPPET_WORDS


def occurs_as_phrase(value: str, snippet: str) -> bool:
    """True when `value` occurs in the snippet on word boundaries: "Ankara" is in "Ankara'da"
    (a suffix after an apostrophe), "Ank" is not."""
    key = snippet_key(value)
    if not key:
        return False
    return re.search(rf"(?<!\w){re.escape(key)}(?!\w)", match_key(snippet)) is not None


# -- instruction-like page lines -------------------------------------------------------------

# Page lines addressed to a model ("note to the AI", "AI:", "ignore the previous ...") are
# never evidence, even when the model quotes them exactly.
_INSTRUCTION_RE = re.compile(
    r"\b(?:note|message|instructions?)\s+(?:to|for)\s+(?:the\s+)?(?:ai|llm|model|assistant|bot)\b"
    r"|\b(?:ai|llm|assistant)\s*:"
    r"|\bignore\s+(?:all\s+|any\s+)?(?:the\s+)?(?:previous|prior|above)\b"
)


def looks_like_instruction(text: str) -> bool:
    return _INSTRUCTION_RE.search(match_key(text)) is not None


def page_evidence_key(text: str) -> str:
    """`match_key` of the page text without instruction-like lines."""
    lines = [line for line in text.splitlines() if not looks_like_instruction(line)]
    return match_key("\n".join(lines))


# -- URLs ------------------------------------------------------------------------------------

_URL_RE = re.compile(r"https?://[^\s<>\"'()\[\]]+", re.IGNORECASE)


def url_in_text(value: str, text: str) -> bool:
    """True when `text` (raw, not `match_key`: that drops "_") writes an absolute URL equal
    to `value` after `normalize_url`. "https://site.co" does not match "https://site.com/x"."""
    target = normalize_url(value)
    return any(normalize_url(url.rstrip(".,;:!?")) == target for url in _URL_RE.findall(text))


# -- page spans for the evidence fallback ----------------------------------------------------

SPAN_MAX_CHARS = 300
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")


def evidence_spans(text: str) -> list[str]:
    """Page lines (long lines split into sentences, long sentences into overlapping word
    windows) of at most SPAN_MAX_CHARS, in page order, without instruction-like lines and
    spans too short to be evidence."""
    spans: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or looks_like_instruction(line):
            continue
        parts = [line] if len(line) <= SPAN_MAX_CHARS else _SENTENCE_END_RE.split(line)
        for part in parts:
            part = part.strip()
            windows = [part] if len(part) <= SPAN_MAX_CHARS else _word_windows(part)
            spans += [window for window in windows if long_enough(window)]
    return spans


def _word_windows(sentence: str) -> list[str]:
    """Windows of whole words, at most SPAN_MAX_CHARS each, starting every half window: any
    stretch of up to SPAN_MAX_CHARS / 2 characters lies whole inside one window."""
    words = sentence.split()
    windows: list[str] = []
    start = 0
    while start < len(words):
        end, length = start, 0
        while end < len(words) and length + len(words[end]) + (end > start) <= SPAN_MAX_CHARS:
            length += len(words[end]) + (end > start)
            end += 1
        if end == start:  # one word longer than a window: not evidence
            start += 1
            continue
        windows.append(" ".join(words[start:end]))
        if end == len(words):
            break
        # Next window starts at the first word past the half of this one.
        half, step = 0, start
        while step < end and half < SPAN_MAX_CHARS // 2:
            half += len(words[step]) + 1
            step += 1
        start = max(step, start + 1)
    return windows


# -- keywords: format, fee, currency, country ------------------------------------------------

_WORD_RE = re.compile(r"[a-z]+")

_FORMAT_KEYWORDS = {
    "online": re.compile(r"\b(?:online|cevrimici|uzaktan|virtual|remote)"),
    "in_person": re.compile(r"\b(?:yuz yuze|fiziksel|in[- ]person|on[- ]?site)"),
    "hybrid": re.compile(r"\b(?:hibrit|hybrid)"),
}


def supports_format(value: str, snippet: str) -> bool:
    text = fold_turkish(match_key(snippet))
    if value == "hybrid" and all(
        _FORMAT_KEYWORDS[kind].search(text) for kind in ("online", "in_person")
    ):
        return True
    keywords = _FORMAT_KEYWORDS.get(value)
    return keywords is not None and keywords.search(text) is not None


_NEGATIONS = frozenset(
    {"no", "not", "without", "zero", "yok", "alinmaz", "alinmayacak", "alinmamaktadir"}
)
# "Free" and "fee" count only when they are about taking part. Turkish: "ücretsiz", "ücret"
# within a few words of "katılım", "başvuru", "etkinlik" ("Etkinliğimiz tamamen
# ücretsizdir", "katılım ücreti"). English, where "free" is everywhere ("feel free", "free
# food", "free-tier credits"): fixed phrases ("participation is free", "free to attend",
# "free of charge", "registration fee").
_PARTICIPATION_PREFIXES = (
    "katil", "basvur", "kayit", "etkinlik", "etkinlig", "yarisma", "hackathon", "giris",
)  # fmt: skip
_PARTICIPATION_WINDOW = 3  # words between "ücretsiz"/"ücret" and the participation word
_TAKING_PART = r"(?:join|enter|participate|attend|register|apply|take part)"
_FREE_EN_RE = re.compile(
    rf"(?<!feel )\bfree (?:to {_TAKING_PART}\b|of charge\b|(?:entry|admission|registration"
    r"|participation)\b)"
    r"|\b(?:participation|entry|admission|registration|attendance|tickets?|event|hackathon"
    r"|competition|joining|attending|participating) (?:is|are) "
    r"(?:(?:completely|totally|entirely|absolutely|100%) )?free\b"
)
_FEE_EN_RE = re.compile(
    r"\b(?:participation|entry|registration|admission|attendance|application|ticket) fees?\b"
    rf"|\bfees? (?:to {_TAKING_PART}|for (?:participation|registration|entry))\b"
)


def supports_is_free(value: bool, snippet: str) -> bool:
    """A free-to-take-part phrase supports True; a fee phrase supports False unless negated
    ("ücret alınmaz", "no registration fee", "zero participation fee"), which supports True.
    See _PARTICIPATION_PREFIXES for what counts as about taking part."""
    text = fold_turkish(match_key(snippet))
    words = _WORD_RE.findall(text)

    def tied(index: int) -> bool:
        low, high = max(0, index - _PARTICIPATION_WINDOW), index + _PARTICIPATION_WINDOW + 1
        return any(
            w.startswith(_PARTICIPATION_PREFIXES)
            for i, w in enumerate(words[low:high], start=low)
            if i != index
        )

    free = _FREE_EN_RE.search(text) is not None or any(
        (w.startswith("ucretsiz") or w == "bedava") and tied(i) for i, w in enumerate(words)
    )
    fee = _FEE_EN_RE.search(text) is not None or any(
        w.startswith("ucret") and not w.startswith("ucretsiz") and tied(i)
        for i, w in enumerate(words)
    )
    negated = fee and any(w in _NEGATIONS for w in words)
    if value:
        return free or negated
    return fee and not free and not negated


_CURRENCY_MARKERS: dict[str, tuple[frozenset[str], str]] = {
    "TRY": (frozenset({"tl", "try", "lira"}), chr(0x20BA)),  # ₺
    "USD": (frozenset({"usd", "dolar", "dollar", "dollars"}), "$"),
    "EUR": (frozenset({"eur", "euro", "avro"}), chr(0x20AC)),  # €
    "GBP": (frozenset({"gbp", "sterlin", "pound", "pounds"}), chr(0xA3)),  # £
    "INR": (frozenset({"inr", "rupee", "rupees", "rupi"}), chr(0x20B9)),  # ₹
}
_CURRENCY_WORDS = frozenset().union(*(words for words, _ in _CURRENCY_MARKERS.values()))
_CURRENCY_SYMBOLS = "".join(symbol for _, symbol in _CURRENCY_MARKERS.values())


def supports_currency(code: str, snippet: str) -> bool:
    text = fold_turkish(match_key(snippet))
    words = set(_WORD_RE.findall(text))
    if code.lower() in words:
        return True
    marker_words, symbol = _CURRENCY_MARKERS.get(code, (frozenset(), ""))
    return bool(words & marker_words) or (bool(symbol) and symbol in text)


# Country names, folded. Turkish names match as a word prefix ("Türkiye'de", "Almanyada");
# English names as whole words ("India", not "Indiana"). The countries events on the import
# list come from; others need the ISO code on the page. Ambiguous names are left out
# ("Georgia" is also a US state, "mısır" is also corn).
_COUNTRY_NAMES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "TR": (("turkiye",), ("turkey",)),
    "AZ": (("azerbaycan",), ("azerbaijan",)),
    "DE": (("almanya",), ("germany", "deutschland")),
    "FR": (("fransa",), ("france",)),
    "GB": (("ingiltere", "birlesik krallik"), ("england", "united kingdom", "uk")),
    "GR": (("yunanistan",), ("greece",)),
    "NL": (("hollanda",), ("netherlands",)),
    "US": (("abd", "amerika"), ("usa", "united states")),
    "IT": (("italya",), ("italy", "italia")),
    "ES": (("ispanya",), ("spain",)),
    "PT": (("portekiz",), ("portugal",)),
    "BE": (("belcika",), ("belgium",)),
    "CH": (("isvicre",), ("switzerland",)),
    "AT": (("avusturya",), ("austria",)),
    "PL": (("polonya",), ("poland",)),
    "SE": (("isvec",), ("sweden",)),
    "NO": (("norvec",), ("norway",)),
    "DK": (("danimarka",), ("denmark",)),
    "FI": (("finlandiya",), ("finland",)),
    "IE": (("irlanda",), ("ireland",)),
    "BG": (("bulgaristan",), ("bulgaria",)),
    "RO": (("romanya",), ("romania",)),
    "UA": (("ukrayna",), ("ukraine",)),
    "CY": (("kibris",), ("cyprus",)),
    "EG": ((), ("egypt",)),
    "AE": (("birlesik arap emirlik",), ("united arab emirates", "uae")),
    "SA": (("suudi arabistan",), ("saudi arabia",)),
    "QA": ((), ("qatar",)),
    "IN": (("hindistan",), ("india",)),
    "PK": (("pakistan",), ("pakistan",)),
    "JP": (("japonya",), ("japan",)),
    "KR": (("guney kore",), ("south korea",)),
    "CA": (("kanada",), ("canada",)),
    "BR": (("brezilya",), ("brazil",)),
    "AU": (("avustralya",), ("australia",)),
    "NG": (("nijerya",), ("nigeria",)),
    "KZ": (("kazakistan",), ("kazakhstan",)),
    "UZ": (("ozbekistan",), ("uzbekistan",)),
}


def supports_country(code: str, snippet: str) -> bool:
    text = fold_turkish(match_key(snippet))
    if code.lower() in _WORD_RE.findall(text):
        return True
    prefixes, words = _COUNTRY_NAMES.get(code, ((), ()))
    return any(re.search(rf"\b{re.escape(name)}", text) for name in prefixes) or any(
        re.search(rf"\b{re.escape(name)}\b", text) for name in words
    )


# -- dates -----------------------------------------------------------------------------------

# Full month names (Turkish folded to ASCII, English) match as a word prefix, so suffixes such
# as "Ekim'e", "Ekimde" or "Aralığa" (k→ğ: "aralig") are covered. Abbreviations ("may",
# "ara", "kas" are also ordinary words) count only next to a day number.
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
# Words allowed between the days of a range: "5 ve 6 Ekim", "October 5 and 6".
_RANGE_WORDS = frozenset({"ve", "ile", "ila", "and", "to", "through", "thru"})
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_DMY_DATE_RE = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4}|\d{2})\b")
_TOKEN_RE = re.compile(rf"\d+|[a-z]+|[{re.escape(_CURRENCY_SYMBOLS)}]")

# A date without a year stays in the fetch year unless that puts it more than this far
# before the fetch date; then it is next year ("10 Ocak" fetched in October → next January).
YEAR_LOOKBACK = timedelta(days=90)


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


def _full_month(word: str) -> int | None:
    return next((month for prefix, month in _MONTH_PREFIXES if word.startswith(prefix)), None)


@dataclass(frozen=True)
class _DateTokens:
    days: dict[int, int]  # token index → day number
    months: dict[int, int]  # token index → month
    years: set[int]
    connectors: set[int]  # token indexes of _RANGE_WORDS


def _is_currency(token: str) -> bool:
    return token in _CURRENCY_WORDS or token in _CURRENCY_SYMBOLS


def _date_tokens(text: str) -> _DateTokens:
    tokens = _TOKEN_RE.findall(text)

    def amount(i: int) -> bool:  # "2000 TL", "$500": a number next to a currency marker
        return (i + 1 < len(tokens) and _is_currency(tokens[i + 1])) or (
            i > 0 and tokens[i - 1] in _CURRENCY_SYMBOLS
        )

    days: dict[int, int] = {}
    years: set[int] = set()
    for i, token in enumerate(tokens):
        if not token.isdigit() or amount(i):
            continue
        if len(token) <= 2 and 1 <= int(token) <= 31:
            days[i] = int(token)
        elif len(token) == 4 and 1900 <= int(token) <= 2100:
            years.add(int(token))
    months: dict[int, int] = {}
    for i, token in enumerate(tokens):
        if not token.isalpha():
            continue
        month = _full_month(token)
        if month is None and token in _MONTH_ABBREVIATIONS and (i - 1 in days or i + 1 in days):
            month = _MONTH_ABBREVIATIONS[token]
        if month is not None:
            months[i] = month
    connectors = {i for i, token in enumerate(tokens) if token in _RANGE_WORDS}
    return _DateTokens(days, months, years, connectors)


def _day_month_pairs(found: _DateTokens) -> set[tuple[int, int]]:
    """(day, month) pairs, each day joined to its own month: "30 Eylül - 2 Ekim" gives
    (30, 9) and (2, 10), never (2, 9). The order (day-month or month-day) is the one the
    snippet uses most for adjacent tokens; ties go to the Turkish day-month order."""
    day_first = sum(1 for i in found.days if i + 1 in found.months)
    month_first = sum(1 for i in found.days if i - 1 in found.months)
    if not (day_first or month_first):
        return set()
    step = 1 if day_first >= month_first else -1
    pairs: set[tuple[int, int]] = set()
    for i, day in found.days.items():
        j = i + step
        while j in found.days or j in found.connectors:  # the other days of a range
            j += step
        if j in found.months:
            pairs.add((day, found.months[j]))
    return pairs


@dataclass(frozen=True)
class DateEvidence:
    value: date | None  # None: the snippet does not support the date
    year_inferred: bool = False
    reason: str = ""


def check_date(value: date, snippet: str, fetch_date: date) -> DateEvidence:
    """Check that the snippet states `value`'s day next to its month; take the year from the
    snippet when it has one, else from `resolve_year` (the model's year is then ignored)."""
    text = fold_turkish(match_key(snippet))
    numeric = [(int(d), int(m), int(y)) for y, m, d in _ISO_DATE_RE.findall(text)] + [
        (int(d), int(m), int(y) + 2000 if len(y) == 2 else int(y))
        for d, m, y in _DMY_DATE_RE.findall(text)
    ]
    found = _date_tokens(_DMY_DATE_RE.sub(" ", _ISO_DATE_RE.sub(" ", text)))
    years = found.years | {y for _, _, y in numeric}

    if (value.day, value.month) not in _day_month_pairs(found) | {(d, m) for d, m, _ in numeric}:
        return DateEvidence(None, reason="the snippet does not give this day and month")

    if years:
        if value.year not in years:
            return DateEvidence(None, reason="the year is not in the snippet")
        return DateEvidence(value)
    resolved = resolve_year(value.month, value.day, fetch_date)
    if resolved is None:
        return DateEvidence(None, reason="the day does not exist in the inferred year")
    return DateEvidence(resolved, year_inferred=True)


# -- numbers ---------------------------------------------------------------------------------

_NUMBER_RE = re.compile(r"\d+")
_NUMBER_WORDS = {
    "tek": 1, "bireysel": 1, "solo": 1, "single": 1, "individual": 1, "individually": 1,
    "iki": 2, "two": 2, "uc": 3, "three": 3, "dort": 4, "four": 4, "bes": 5, "five": 5,
    "alti": 6, "six": 6, "yedi": 7, "seven": 7, "sekiz": 8, "eight": 8, "dokuz": 9,
    "nine": 9, "ten": 10,
}  # fmt: skip


_TEAM_WORDS = ("takim", "kisi", "ekip", "uye", "team", "member", "people", "person")


_SOLO_NUMBER_RE = re.compile(r"(?<![\d.,])1 (?:kisi|person|member|participant)")


def mentions_team_size(value: int, snippet: str) -> bool:
    """True when the snippet talks about teams ("takım", "kişi", "team", ...) and writes
    `value` as a number or a number word (1-10)."""
    text = fold_turkish(match_key(snippet))
    words = _WORD_RE.findall(text)
    if not any(word.startswith(_TEAM_WORDS) for word in words):
        return False
    if value == 1:
        # A bare "1" is everywhere ("1 dk demo", "1. Ödül"): one person needs a solo word
        # ("bireysel", "individually") or "1 kişi" / "1 person".
        return any(_NUMBER_WORDS.get(word) == 1 for word in words) or (
            _SOLO_NUMBER_RE.search(text) is not None
        )
    if value in {int(n) for n in _NUMBER_RE.findall(snippet)}:
        return True
    return any(_NUMBER_WORDS.get(word) == value for word in words)


_AMOUNT_RE = re.compile(
    r"(?<![\d.,])(\d+(?:[.,]\d+)*)(?!\d)(?:\s*(bin|thousand|milyon|million|mn|k|m)(?![a-z]))?"
)
_MULTIPLIERS = {
    "bin": 1000, "thousand": 1000, "k": 1000,
    "milyon": 1_000_000, "million": 1_000_000, "mn": 1_000_000, "m": 1_000_000,
}  # fmt: skip
_CURRENCY_AFTER_RE = re.compile(
    rf"\s*(?:[{re.escape(_CURRENCY_SYMBOLS)}]|(?:{'|'.join(sorted(_CURRENCY_WORDS))})(?![a-z]))"
)
_PRIZE_RE = re.compile(r"odul|prize|award|reward")
_PRIZE_WINDOW = 30  # characters around an amount that may name the prize


def _parse_number(token: str) -> set[Decimal]:
    """Readings of "50.000", "50,000", "1,5", "1.234,56", "2,25,000": a separator followed
    by exactly three digits is a thousands separator (in Indian grouping, two-digit groups
    before the last three: lakh, crore); otherwise the last separator is the decimal one."""
    groups = re.split(r"[.,]", token)
    readings: set[Decimal] = set()
    if len(groups) > 1 and all(len(group) == 3 for group in groups[1:]):
        readings.add(Decimal("".join(groups)))
    if len(groups) > 2 and len(groups[-1]) == 3 and all(len(g) == 2 for g in groups[1:-1]):
        readings.add(Decimal("".join(groups)))
    if len(groups) > 1:
        readings.add(Decimal(f"{''.join(groups[:-1])}.{groups[-1]}"))
    else:
        readings.add(Decimal(token))
    return readings


def mentions_amount(value: Decimal, snippet: str) -> bool:
    """True when the snippet writes `value` as a prize amount ("50.000 TL", "$10K", "1,5
    milyon TL ödül"): next to a currency marker, or near "ödül"/"prize". A bare year-like
    number ("Hackathon 2026") needs the currency marker itself."""
    text = fold_turkish(match_key(snippet))
    for match in _AMOUNT_RE.finditer(text):
        token, suffix = match.group(1), match.group(2) or ""
        start, end = match.span()
        before = text[:start].rstrip(" \"'")[-1:]  # "₺50.000", "$ 10K"
        currency = _CURRENCY_AFTER_RE.match(text, end) is not None or (
            bool(before) and before in _CURRENCY_SYMBOLS
        )
        year_like = not suffix and len(token) == 4 and token.isdigit()
        if year_like and not currency:
            continue
        window = text[max(0, start - _PRIZE_WINDOW) : end + _PRIZE_WINDOW]
        if not currency and _PRIZE_RE.search(window) is None:
            continue
        multiplier = _MULTIPLIERS.get(suffix, 1)
        if any(reading * multiplier == value for reading in _parse_number(token)):
            return True
    return False

"""KVKK guard for cloud LLM calls (D-22, D-23; OPENAI_API_RESEARCH §1).

`mask_pii` replaces e-mail addresses (including Unicode/IDN domains), phone numbers (Turkish
formats and other `+`-prefixed international numbers) and 11-digit numbers that pass the TC
Kimlik checksum with fixed placeholders. The OpenAI provider runs every outbound system and
user string through it before the HTTP call. Extraction does not need these values; a field
whose evidence was masked is simply dropped by the evidence check.

Deliberate choices:
- A bare 10-digit number starting with 5 (`5321234567`) is masked: it is the shape of a
  Turkish mobile number written without a prefix.
- A TC Kimlik number is found even when glued to letters (`TC10000000146`); the checksum keeps
  false positives rare.
- Spans that contain a date (`2026-10-13`, `13.10.2026`) are never masked as phone numbers, so
  `UTC +3 2026-10-13` keeps its date.
- IBANs are not masked (not needed for extraction, and organiser bank details are public).
- The untrusted-envelope markers (`<<<…>>>`) are left untouched, so the random boundary id
  can never be altered by a mask.

This is a first line only. Application data (community/team applications) must never reach an
LLM at all; an architecture test keeps the application code paths from importing `fhc_api.llm`.
"""

import re

EMAIL_PLACEHOLDER = "[email]"
PHONE_PLACEHOLDER = "[phone]"
TC_KIMLIK_PLACEHOLDER = "[tc_kimlik]"

# \w is Unicode-aware: Turkish letters (also uppercase İ, Ş, Ğ) and IDN domains match.
_EMAIL_RE = re.compile(r"[\w.%+\-]+@[\w\-]+(?:\.[\w\-]+)*\.[^\W\d_]{2,}")
_TC_CANDIDATE_RE = re.compile(r"(?<!\d)[1-9]\d{10}(?!\d)")
_SEP = r"[ .\-]?"
# Turkish numbers: with a +90 / 0090 / 0 prefix any area code 2xx-5xx; with a bare 90 prefix or
# without a prefix only mobile numbers (5xx), so that bare amounts starting with 2-4 are kept.
_TR_PHONE_RE = re.compile(
    r"(?<![0-9A-Za-z+])"
    r"(?:(?:(?:\+|00)90|0)" + _SEP + r"\(?[2-5]\d{2}\)?"
    r"|90" + _SEP + r"\(?5\d{2}\)?"
    r"|\(?5\d{2}\)?)"
    rf"{_SEP}\d{{3}}{_SEP}\d{{2}}{_SEP}\d{{2}}"
    r"(?![0-9A-Za-z])"
)
# Other international numbers: `+`, a 1-3 digit country code without a leading zero, then 2-5
# groups of digits (an optional parenthesised area code) separated by single spaces, dots or
# hyphens; 8-15 digits in total.
_INTL_PHONE_RE = re.compile(
    r"(?<![0-9A-Za-z+])\+[1-9]\d{0,2}(?:[ .\-]?(?:\(\d{1,4}\)|\d{1,4})){2,5}(?![0-9A-Za-z])"
)
_MIN_INTL_DIGITS = 8
_MAX_INTL_DIGITS = 15
_DATE_RE = re.compile(r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}\.\d{1,2}\.\d{4}|\d{1,2}/\d{1,2}/\d{4}")
_MARKER_RE = re.compile(r"(<<<[A-Za-z0-9_]+>>>)")


def is_valid_tc_kimlik(number: str) -> bool:
    """True for an 11-digit string with a non-zero first digit and valid check digits."""
    if len(number) != 11 or not number.isascii() or not number.isdigit() or number[0] == "0":
        return False
    d = [int(c) for c in number]
    odd = d[0] + d[2] + d[4] + d[6] + d[8]
    even = d[1] + d[3] + d[5] + d[7]
    return (odd * 7 - even) % 10 == d[9] and sum(d[:10]) % 10 == d[10]


def _mask_tc(match: re.Match[str]) -> str:
    return TC_KIMLIK_PLACEHOLDER if is_valid_tc_kimlik(match.group()) else match.group()


def _mask_tr_phone(match: re.Match[str]) -> str:
    return match.group() if _DATE_RE.search(match.group()) else PHONE_PLACEHOLDER


def _mask_intl(match: re.Match[str]) -> str:
    span = match.group()
    digits = sum(c.isdigit() for c in span)
    if _DATE_RE.search(span) or not _MIN_INTL_DIGITS <= digits <= _MAX_INTL_DIGITS:
        return span
    return PHONE_PLACEHOLDER


def _mask_segment(text: str) -> str:
    text = _EMAIL_RE.sub(EMAIL_PLACEHOLDER, text)
    text = _TC_CANDIDATE_RE.sub(_mask_tc, text)
    text = _TR_PHONE_RE.sub(_mask_tr_phone, text)
    return _INTL_PHONE_RE.sub(_mask_intl, text)


def mask_pii(text: str) -> str:
    """Return `text` with e-mails, phone numbers and TC Kimlik numbers replaced."""
    # re.split with a capturing group: odd indexes are the envelope markers, kept verbatim.
    parts = _MARKER_RE.split(text)
    return "".join(part if i % 2 else _mask_segment(part) for i, part in enumerate(parts))

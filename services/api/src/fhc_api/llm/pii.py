"""KVKK guard for cloud LLM calls (D-22, D-23; OPENAI_API_RESEARCH §1).

`mask_pii` replaces e-mail addresses, phone numbers (Turkish formats and other `+`-prefixed
international numbers) and 11-digit numbers that pass the TC Kimlik checksum with fixed
placeholders. The OpenAI provider runs every outbound system and user string through it before
the HTTP call. Extraction does not need these values; a field whose evidence was masked is
simply dropped by the evidence check.

This is a first line only. Application data (community/team applications) must never reach an
LLM at all; an architecture test keeps the applications module from importing `fhc_api.llm`.

Number patterns refuse to start or end next to a letter or digit, so hex ids (the untrusted
envelope boundary) and longer digit runs are left alone.
"""

import re

EMAIL_PLACEHOLDER = "[email]"
PHONE_PLACEHOLDER = "[phone]"
TC_KIMLIK_PLACEHOLDER = "[tc_kimlik]"

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
_TC_CANDIDATE_RE = re.compile(r"(?<![0-9A-Za-z])[1-9]\d{10}(?![0-9A-Za-z])")
_SEP = r"[ .\-]?"
# Turkish numbers: with a +90 / 0090 / 0 prefix any area code 2xx-5xx; without a prefix only
# mobile numbers (5xx), so that bare 10-digit amounts starting with 2-4 are not touched.
_TR_PHONE_RE = re.compile(
    r"(?<![0-9A-Za-z+])"
    r"(?:(?:(?:\+|00)90|0)" + _SEP + r"\(?[2-5]\d{2}\)?|\(?5\d{2}\)?)"
    rf"{_SEP}\d{{3}}{_SEP}\d{{2}}{_SEP}\d{{2}}"
    r"(?![0-9A-Za-z])"
)
# Other international numbers: a `+`, then 8-15 digits with optional separators.
_INTL_PHONE_RE = re.compile(r"(?<![0-9A-Za-z+])\+\d[\d ().\-]{6,22}\d(?![0-9A-Za-z])")
_MIN_INTL_DIGITS = 8
_MAX_INTL_DIGITS = 15


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


def _mask_intl(match: re.Match[str]) -> str:
    digits = sum(c.isdigit() for c in match.group())
    if _MIN_INTL_DIGITS <= digits <= _MAX_INTL_DIGITS:
        return PHONE_PLACEHOLDER
    return match.group()


def mask_pii(text: str) -> str:
    """Return `text` with e-mails, phone numbers and TC Kimlik numbers replaced."""
    text = _EMAIL_RE.sub(EMAIL_PLACEHOLDER, text)
    text = _TC_CANDIDATE_RE.sub(_mask_tc, text)
    text = _TR_PHONE_RE.sub(PHONE_PLACEHOLDER, text)
    return _INTL_PHONE_RE.sub(_mask_intl, text)

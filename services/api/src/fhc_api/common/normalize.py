"""Deterministic normalization shared by the API, imports and duplicate checks."""

import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit

_TR_ASCII = str.maketrans(
    {
        "ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
        "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
        "â": "a", "Â": "a", "î": "i", "Î": "i", "û": "u", "Û": "u",
    }
)  # fmt: skip

_TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src"}

SLUG_MAX_LENGTH = 80


def fold_turkish(text: str) -> str:
    """Lower-case ASCII folding that treats Turkish letters correctly (İ→i, ı→i)."""
    text = text.translate(_TR_ASCII)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()


def slugify(text: str, max_length: int = SLUG_MAX_LENGTH) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", fold_turkish(text)).strip("-")
    return slug[:max_length].strip("-") or "event"


def fold_title(text: str) -> str:
    """Title comparison key: Turkish-folded words separated by single spaces."""
    return " ".join(re.findall(r"[a-z0-9]+", fold_turkish(text)))


_DEFAULT_PORTS = {"http": 80, "https": 443}


def normalize_url(url: str) -> str:
    """Comparable form of a URL: host without www, path without trailing slash,
    tracking parameters removed, remaining query sorted. Scheme and fragment dropped;
    the port is kept only when it is not the scheme's default."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if ":" in host:  # IPv6 literal: keep the brackets so a port stays unambiguous
        host = f"[{host}]"
    if parts.port and parts.port != _DEFAULT_PORTS.get(parts.scheme.lower()):
        host = f"{host}:{parts.port}"
    path = re.sub(r"/{2,}", "/", parts.path).rstrip("/")
    # Percent-escapes are case-insensitive (RFC 3986 §6.2.2.1): %2f == %2F.
    path = re.sub(r"%[0-9a-fA-F]{2}", lambda match: match.group(0).upper(), path)
    query = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_PARAMS
    )
    return host + path + (f"?{urlencode(query)}" if query else "")

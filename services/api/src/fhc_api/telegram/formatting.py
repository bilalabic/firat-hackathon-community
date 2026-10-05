"""Strict HTML helpers for `parse_mode=HTML` (TELEGRAM_RESEARCH §2.6).

Bot API "HTML style": all `<`, `>` and `&` that are not part of a tag or entity must be
replaced with `&lt;`, `&gt;` and `&amp;`. Supported named entities are only `&lt;`, `&gt;`,
`&amp;` and `&quot;`. Only our templates add tags; every dynamic value goes through these helpers.
"""

from urllib.parse import urlsplit


def escape_html(text: str) -> str:
    """Escape text content: `&` first, then `<` and `>`. Quotes are left as is."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _escape_attribute(value: str) -> str:
    return escape_html(value).replace('"', "&quot;")


def is_safe_http_url(url: str) -> bool:
    """True for an absolute http(s) URL with a host and no whitespace or control characters."""
    if not url or any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in url):
        return False
    try:
        parts = urlsplit(url)
        hostname = parts.hostname
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and bool(hostname) and parts.netloc != ""


def html_link(url: str, label: str) -> str:
    """Build `<a href="url">label</a>`; raise ValueError unless the URL is a safe http(s) URL."""
    if not is_safe_http_url(url):
        raise ValueError("Only absolute http(s) URLs can be linked.")
    return f'<a href="{_escape_attribute(url)}">{escape_html(label)}</a>'

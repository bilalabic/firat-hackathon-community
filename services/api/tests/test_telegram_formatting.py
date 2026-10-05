import pytest

from fhc_api.telegram.formatting import escape_html, html_link, is_safe_http_url


@pytest.mark.parametrize(
    ("raw", "escaped"),
    [
        ("a & b", "a &amp; b"),
        ("<b>x</b>", "&lt;b&gt;x&lt;/b&gt;"),
        ("&lt;", "&amp;lt;"),
        ("\"quotes\" and 'apostrophes'", "\"quotes\" and 'apostrophes'"),
        ("Fırat Üniversitesi — Elazığ", "Fırat Üniversitesi — Elazığ"),
        ("", ""),
    ],
)
def test_escape_html(raw: str, escaped: str) -> None:
    assert escape_html(raw) == escaped


def test_escape_is_not_idempotent_by_design() -> None:
    # Escape exactly once, at render time.
    assert escape_html(escape_html("&")) == "&amp;amp;"


def test_html_link_escapes_href_and_label() -> None:
    link = html_link('https://example.com/?a=1&b="x"<y>', "<Başvur & Katıl>")
    assert link == (
        '<a href="https://example.com/?a=1&amp;b=&quot;x&quot;&lt;y&gt;">'
        "&lt;Başvur &amp; Katıl&gt;</a>"
    )


@pytest.mark.parametrize(
    "url",
    ["https://firathackathon.com/events/x", "http://example.com", "https://a.b/c?d=e#f"],
)
def test_safe_urls(url: str) -> None:
    assert is_safe_http_url(url)
    assert html_link(url, "x").startswith(f'<a href="{url.replace("&", "&amp;")}">')


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "JAVASCRIPT:alert(1)",
        "tg://user?id=1",
        "data:text/html,<b>x</b>",
        "ftp://example.com",
        "//example.com/x",
        "/relative",
        "https://",
        "https://exa mple.com",
        "https://example.com/\nx",
        "https://example.com/\x00",
        "https://[::1",
        "",
    ],
)
def test_unsafe_urls_rejected(url: str) -> None:
    assert not is_safe_http_url(url)
    with pytest.raises(ValueError):
        html_link(url, "x")

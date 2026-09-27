import pytest

from fhc_api.common.normalize import fold_turkish, normalize_url, slugify


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("İSTANBUL", "istanbul"),
        ("Işık Üniversitesi", "isik universitesi"),
        ("Çağrı Göğüş Şenol", "cagri gogus senol"),
    ],
)
def test_fold_turkish(text: str, expected: str) -> None:
    assert fold_turkish(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Borsa İstanbul Fintech Hackathon", "borsa-istanbul-fintech-hackathon"),
        ("Greece–Türkiye Hackathon 2026", "greece-turkiye-hackathon-2026"),  # noqa: RUF001 real legacy title
        ("DevNetwork [API + Cloud + AI] Hackathon 2026", "devnetwork-api-cloud-ai-hackathon-2026"),
        ("!!!", "event"),
    ],
)
def test_slugify(text: str, expected: str) -> None:
    assert slugify(text) == expected


def test_slugify_respects_max_length_without_trailing_dash() -> None:
    slug = slugify("a " * 100, max_length=9)
    assert slug == "a-a-a-a-a"
    assert len(slug) <= 9


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "https://www.Patika.dev/bootcamp/grid-up-hackathon/",
            "patika.dev/bootcamp/grid-up-hackathon",
        ),
        ("http://patika.dev/bootcamp/grid-up-hackathon", "patika.dev/bootcamp/grid-up-hackathon"),
        ("https://example.com/e?utm_source=x&b=2&a=1&fbclid=z#top", "example.com/e?a=1&b=2"),
        ("https://example.com:443/", "example.com"),
        ("https://example.com:8443/x", "example.com:8443/x"),
        ("https://example.com//a//b/", "example.com/a/b"),
    ],
)
def test_normalize_url(url: str, expected: str) -> None:
    assert normalize_url(url) == expected


def test_normalize_url_keeps_path_case() -> None:
    assert normalize_url("https://example.com/Event") == "example.com/Event"

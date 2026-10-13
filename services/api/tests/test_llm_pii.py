"""KVKK guard: masking before cloud LLM calls (llm/pii.py)."""

import pytest

from fhc_api.llm.pii import is_valid_tc_kimlik, mask_pii
from fhc_api.llm.untrusted import wrap_untrusted


@pytest.mark.parametrize(
    "email",
    ["info@example.com", "ad.soyad+etkinlik@firat.edu.tr", "X_Y-1@sub.domain.co"],
)
def test_emails_are_masked(email: str) -> None:
    assert mask_pii(f"İletişim: {email}.") == "İletişim: [email]."


@pytest.mark.parametrize(
    "phone",
    [
        "+90 532 123 45 67",
        "+905321234567",
        "0090 532 123 45 67",
        "0532 123 45 67",
        "0 (532) 123 45 67",
        "05321234567",
        "(532) 123-45-67",
        "532 123 4567",
        "0424 237 00 00",
        "+90 (424) 237-0000",
        "+49 30 1234 5678",
        "+1 (415) 555-0100",
    ],
)
def test_phone_numbers_are_masked(phone: str) -> None:
    assert mask_pii(f"Tel: {phone} (mesai)") == "Tel: [phone] (mesai)"


def test_tc_kimlik_checksum() -> None:
    assert is_valid_tc_kimlik("10000000146")
    assert not is_valid_tc_kimlik("10000000147")
    assert not is_valid_tc_kimlik("01234567890")
    assert not is_valid_tc_kimlik("1000000014")


def test_valid_tc_kimlik_is_masked_and_other_11_digit_numbers_are_kept() -> None:
    assert mask_pii("TC: 10000000146") == "TC: [tc_kimlik]"
    assert mask_pii("Ref 10000000147") == "Ref 10000000147"


@pytest.mark.parametrize(
    "text",
    [
        "2026-10-13 ile 2026-10-15 arası",
        "13.10.2026 – 15.10.2026",
        "Ödül havuzu 250.000 TL, 1.000.000 TL büyük ödül",
        "Takımlar 2-5 kişi, kontenjan 120",
        "Saat 09:00 - 18:00",
        "Başvuru no 4242424242424",
        "ISBN 978-3-16-148410-0",
    ],
)
def test_ordinary_numbers_are_kept(text: str) -> None:
    assert mask_pii(text) == text


def test_untrusted_envelope_boundary_survives_masking() -> None:
    boundary = "12345678901" + "a" * 21  # digit run inside a hex id must not be touched
    wrapped = wrap_untrusted("Sayfa 05321234567", boundary=boundary)
    masked = mask_pii(wrapped)
    assert masked.count(boundary) == 2
    assert "05321234567" not in masked


@pytest.mark.parametrize(
    "text",
    [
        "UTC +3 2026-10-13",
        "+3 2026-10-13 18:00",
        "Kontenjan +100 2026-10-13",
        "(GMT +03) 2026-10-13",
        "GMT+3 13.10.2026 09:00",
        "UTC+03:00, 2026-10-13T18:00:00+03:00",
        "+3 13.10.2026",
        "Saat 10:00 (UTC +3), 13/10/2026",
    ],
)
def test_dates_and_timezones_stay_unmasked(text: str) -> None:
    assert mask_pii(text) == text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("TC10000000146", "TC[tc_kimlik]"),
        ("kimlik:10000000146abc", "kimlik:[tc_kimlik]abc"),
        ("90 532 123 45 67", "[phone]"),
        ("905321234567", "[phone]"),
        ("5321234567", "[phone]"),  # documented: a bare 10-digit 5xx number is masked
        ("iletişim@örnek.com.tr", "[email]"),
        ("BİLGİ@FIRAT.EDU.TR", "[email]"),
        ("Şükrü.Öztürk@üniversite.edu.tr", "[email]"),
        ("user@xn--rnek-zoa.com", "[email]"),
    ],
)
def test_harder_pii_shapes_are_masked(text: str, expected: str) -> None:
    assert mask_pii(text) == expected


@pytest.mark.parametrize("iban", ["TR33 0006 1005 1978 6457 8413 26", "TR330006100519786457841326"])
def test_ibans_are_not_masked(iban: str) -> None:
    assert mask_pii(f"IBAN: {iban}") == f"IBAN: {iban}"


def test_envelope_markers_are_never_masked() -> None:
    boundary = "10000000146" + "a" * 21  # a valid TC Kimlik digit run inside the id
    masked = mask_pii(wrap_untrusted("TC 10000000146", boundary=boundary))
    assert masked.count(boundary) == 2
    assert "TC [tc_kimlik]" in masked

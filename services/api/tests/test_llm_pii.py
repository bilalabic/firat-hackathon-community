"""KVKK guard: masking before cloud LLM calls, and no LLM access from the applications domain."""

import ast
from pathlib import Path

import pytest

from fhc_api.llm.pii import is_valid_tc_kimlik, mask_pii
from fhc_api.llm.untrusted import wrap_untrusted

SRC = Path(__file__).resolve().parents[1] / "src" / "fhc_api"


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


# -- architecture -----------------------------------------------------------------------------


def _imported_names(source: str, package: list[str]) -> set[str]:
    """Absolute dotted names a module imports (`from a import b` yields `a` and `a.b`)."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = package[: len(package) - node.level + 1] if node.level else []
            module = ".".join([*base, *([node.module] if node.module else [])])
            names.add(module)
            names.update(f"{module}.{alias.name}" for alias in node.names)
    return names


def _llm_imports(names: set[str]) -> list[str]:
    return sorted(n for n in names if n == "fhc_api.llm" or n.startswith("fhc_api.llm."))


def test_applications_domain_never_imports_the_llm_package() -> None:
    """Community/team applications hold personal data that must never reach an LLM (D-23)."""
    modules = sorted((SRC / "community").rglob("*.py"))
    assert modules, "fhc_api/community not found"
    for path in modules:
        package = ["fhc_api", *path.relative_to(SRC).parent.parts]
        bad = _llm_imports(_imported_names(path.read_text(encoding="utf-8"), package))
        assert not bad, f"{path.relative_to(SRC)} imports {bad}"


def test_import_scanner_catches_every_import_form() -> None:
    source = "from ..llm import openai\nfrom fhc_api import llm\nimport fhc_api.llm.pii\n"
    found = _llm_imports(_imported_names(source, ["fhc_api", "community"]))
    assert found == ["fhc_api.llm", "fhc_api.llm.openai", "fhc_api.llm.pii"]

"""Opt-in smoke test: URL import extraction against a real local Ollama.

Skipped unless FHC_OLLAMA_SMOKE_MODEL is set (e.g. `qwen3.5:0.8b`) and that model is installed.
Run: FHC_OLLAMA_SMOKE_MODEL=qwen3.5:0.8b uv run pytest tests/test_import_extraction_smoke.py -s
"""

import os
from datetime import UTC, datetime

import pytest

from fhc_api.importing.extraction import LLMExtractor
from fhc_api.importing.models import EXTRACTABLE_FIELDS, PageContent
from fhc_api.llm.ollama import OllamaProvider

MODEL = os.environ.get("FHC_OLLAMA_SMOKE_MODEL", "")
BASE_URL = os.environ.get("FHC_OLLAMA_SMOKE_BASE_URL", "http://127.0.0.1:11434")

pytestmark = pytest.mark.skipif(not MODEL, reason="set FHC_OLLAMA_SMOKE_MODEL to run")

PAGE = PageContent(
    requested_url="https://example.org/firat-hackathon",
    final_url="https://example.org/firat-hackathon",
    fetched_at=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
    title="Fırat Hackathon 2026",
    text="""# Fırat Hackathon 2026

Fırat Üniversitesi Yazılım Topluluğu, 24-25 Ekim 2026 tarihlerinde Elazığ'da Fırat \
Hackathon 2026'yı düzenliyor. Etkinlik Fırat Üniversitesi Kongre Merkezi'nde yapılacak.

Son başvuru tarihi: 15 Ekim. Takımlar 2-4 kişiden oluşur. Katılım ücretsizdir.

Toplam ödül havuzu 30.000 TL.
""",
)


def test_real_ollama_extraction() -> None:
    with OllamaProvider(BASE_URL, MODEL, timeout_s=180) as provider:
        health = provider.health()
        if health.status != "ok":
            pytest.skip(f"Ollama not ready: {health.status}: {health.message}")

        result = LLMExtractor(provider, model_label=MODEL).extract(PAGE)

    print(f"\nextracted_by={result.extracted_by} duration_ms={result.llm_duration_ms}")
    print(f"llm_error={result.llm_error}")
    for name, proposal in result.fields.items():
        print(f"  {name} = {proposal.value!r}  <- {proposal.snippet!r}")
    for flag in result.flags:
        print(f"  flag {flag.field}: {flag.kind}: {flag.detail}")
    assert result.llm_error is None, result.llm_error
    assert result.extracted_by == f"llm:{MODEL}"
    assert set(result.fields) <= set(EXTRACTABLE_FIELDS)
    assert all(proposal.snippet for proposal in result.fields.values())

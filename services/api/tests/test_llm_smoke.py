"""Opt-in smoke test against a real local Ollama.

Skipped unless FHC_OLLAMA_SMOKE_MODEL is set (e.g. `qwen3.5:0.8b`) and that model is installed.
Run: FHC_OLLAMA_SMOKE_MODEL=qwen3.5:0.8b uv run pytest tests/test_llm_smoke.py -s
"""

import os

import pytest

from fhc_api.llm.ollama import OllamaProvider
from fhc_api.llm.router import run_llm_check

MODEL = os.environ.get("FHC_OLLAMA_SMOKE_MODEL", "")
BASE_URL = os.environ.get("FHC_OLLAMA_SMOKE_BASE_URL", "http://127.0.0.1:11434")

pytestmark = pytest.mark.skipif(not MODEL, reason="set FHC_OLLAMA_SMOKE_MODEL to run")


def test_real_ollama_check() -> None:
    with OllamaProvider(BASE_URL, MODEL, timeout_s=120) as provider:
        health = provider.health()
        if health.status != "ok":
            pytest.skip(f"Ollama not ready: {health.status}: {health.message}")

        result = run_llm_check(provider)

    print(f"\nhealth={result.health.status} test={result.test}")
    assert result.test is not None
    assert result.test.ok, result.test.error
    assert result.test.output is not None

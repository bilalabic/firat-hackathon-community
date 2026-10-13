"""Opt-in smoke test against the real OpenAI API (costs a few hundred tokens).

Skipped unless FHC_OPENAI_SMOKE=1 and OPENAI_API_KEY are set in the environment (never read
from .env). Optional: FHC_OPENAI_SMOKE_MODEL (default gpt-5.4-mini).
Run: $env:FHC_OPENAI_SMOKE = "1"; uv run pytest tests/test_llm_openai_smoke.py -s
"""

import os

import pytest

from fhc_api.llm.openai import OpenAIProvider
from fhc_api.llm.router import run_llm_check

# Read at import time: the autouse fixture in conftest.py removes Settings-named variables
# (OPENAI_API_KEY among them) from the environment before each test runs.
ENABLED = os.environ.get("FHC_OPENAI_SMOKE") == "1"
API_KEY = os.environ.get("OPENAI_API_KEY", "")
MODEL = os.environ.get("FHC_OPENAI_SMOKE_MODEL", "gpt-5.4-mini")

pytestmark = pytest.mark.skipif(
    not (ENABLED and API_KEY), reason="set FHC_OPENAI_SMOKE=1 and OPENAI_API_KEY to run"
)


def test_real_openai_check() -> None:
    with OpenAIProvider(API_KEY, MODEL, timeout_s=60, daily_token_budget=20_000) as provider:
        result = run_llm_check(provider)
        usage = provider.last_usage

    print(f"\nhealth={result.health.status} test={result.test} usage={usage}")
    assert result.health.status == "ok", result.health.message
    assert result.test is not None
    assert result.test.ok, result.test.error
    assert usage is not None
    assert usage.total_tokens > 0

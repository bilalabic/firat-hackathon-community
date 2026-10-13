"""LLM_PROVIDER picks the provider in create_app; misconfiguration keeps the API up."""

import logging

import pytest
from fastapi.testclient import TestClient

from fhc_api.importing.extraction import LLMExtractor
from fhc_api.llm.ollama import OllamaProvider
from fhc_api.llm.openai import OpenAIProvider
from fhc_api.llm.provider import MisconfiguredProvider
from fhc_api.main import active_llm_model, create_app

from .conftest import AUTH, BASE_URL, make_settings

KEY = "sk-test-LEAKMARKER-0123456789abcdef"


def test_default_provider_is_ollama() -> None:
    settings = make_settings()
    app = create_app(settings)
    assert isinstance(app.state.llm, OllamaProvider)
    assert active_llm_model(settings) == settings.OLLAMA_MODEL


def test_openai_settings_defaults() -> None:
    settings = make_settings()
    assert settings.LLM_PROVIDER == "ollama"
    assert settings.OPENAI_API_KEY is None
    assert settings.OPENAI_MODEL == "gpt-5.4-mini"
    assert settings.OPENAI_BASE_URL == "https://api.openai.com"
    assert settings.OPENAI_REASONING_EFFORT == "none"
    assert settings.OPENAI_DAILY_TOKEN_BUDGET == 2_000_000


def test_openai_is_selected_and_configured_from_settings() -> None:
    settings = make_settings(
        LLM_PROVIDER=" OpenAI ",
        OPENAI_API_KEY=KEY,
        OPENAI_MODEL="gpt-4.1-mini",
        OPENAI_DAILY_TOKEN_BUDGET=1000,
    )
    app = create_app(settings, url_import=True)

    provider = app.state.llm
    assert isinstance(provider, OpenAIProvider)
    assert provider.model == "gpt-4.1-mini"
    assert provider.daily_token_budget == 1000
    assert active_llm_model(settings) == "gpt-4.1-mini"
    extractor = app.state.importer._extractor
    assert isinstance(extractor, LLMExtractor)
    assert extractor._model_label == "gpt-4.1-mini"


def test_openai_without_key_keeps_the_api_up() -> None:
    app = create_app(make_settings(LLM_PROVIDER="openai"))
    client = TestClient(app, base_url=BASE_URL, headers=AUTH)

    assert client.get("/health").status_code == 200
    health = client.get("/llm/check").json()["health"]
    assert health["status"] == "error"
    assert health["provider"] == "openai"
    assert health["configured_model"] == "gpt-5.4-mini"
    assert "OPENAI_API_KEY is not set" in health["message"]


def test_invalid_openai_settings_never_echo_the_key(caplog: pytest.LogCaptureFixture) -> None:
    settings = make_settings(
        LLM_PROVIDER="openai", OPENAI_API_KEY=KEY, OPENAI_REASONING_EFFORT="extreme"
    )
    with caplog.at_level(logging.DEBUG):
        app = create_app(settings)
    assert isinstance(app.state.llm, MisconfiguredProvider)
    health = TestClient(app, base_url=BASE_URL, headers=AUTH).get("/llm/check").json()
    assert "reasoning effort" in health["health"]["message"]
    for text in (str(health), caplog.text):
        assert "LEAKMARKER" not in text


def test_unknown_provider_is_reported() -> None:
    app = create_app(make_settings(LLM_PROVIDER="gemini"))
    health = TestClient(app, base_url=BASE_URL, headers=AUTH).get("/llm/check").json()["health"]
    assert health["status"] == "error"
    assert health["provider"] == "unknown"
    assert "LLM_PROVIDER must be one of" in health["message"]

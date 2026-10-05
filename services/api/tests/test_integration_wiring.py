"""The LLM and Telegram routers are mounted behind the token and wired to settings."""

import logging
from typing import TypeVar

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from fhc_api.llm.ollama import OllamaProvider
from fhc_api.llm.provider import LLMConfigError, MisconfiguredProvider, ProviderHealth
from fhc_api.main import create_app
from fhc_api.telegram.client import TelegramClient

from .conftest import AUTH, BASE_URL, make_settings

T = TypeVar("T", bound=BaseModel)


class DownProvider:
    name = "fake"

    def generate_structured(
        self, *, system: str, user: str, schema: type[T], temperature: float = 0.0
    ) -> T:
        raise AssertionError("must not be called when the provider is down")

    def generate_text(
        self, *, system: str, user: str, max_tokens: int, temperature: float = 0.0
    ) -> str:
        raise AssertionError("must not be called when the provider is down")

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider="fake",
            status="not_running",
            configured_model="m",
            installed_models=[],
            message="down",
        )


def app_client(*, token: bool) -> TestClient:
    app = create_app(make_settings(), llm_provider=DownProvider())
    return TestClient(app, base_url=BASE_URL, headers=AUTH if token else {})


def test_integration_routes_require_the_token() -> None:
    client = app_client(token=False)
    assert client.get("/llm/check").status_code == 401
    assert client.get("/telegram/check").status_code == 401


def test_llm_check_uses_the_injected_provider() -> None:
    body = app_client(token=True).get("/llm/check").json()
    assert body["health"]["status"] == "not_running"
    assert body["test"] is None


def test_telegram_is_not_configured_without_settings() -> None:
    body = app_client(token=True).get("/telegram/check").json()
    assert body["status"] == "not_configured"


def test_settings_defaults_point_at_local_ollama() -> None:
    settings = make_settings()
    assert settings.OLLAMA_BASE_URL == "http://127.0.0.1:11434"
    assert settings.OLLAMA_TIMEOUT_S == 120.0
    assert settings.TELEGRAM_BOT_TOKEN is None


def test_integration_operations_are_in_the_schema() -> None:
    schema = app_client(token=True).get("/openapi.json").json()
    assert schema["paths"]["/llm/check"]["get"]["operationId"] == "llm_check"
    assert schema["paths"]["/telegram/check"]["get"]["operationId"] == "telegram_check"


# --- misconfigured integrations keep the API up ----------------------------------------

LEAK_MARKER = "FakeTestOnlyNotARealBotSecret_0123"


def test_malformed_telegram_token_keeps_the_api_up(caplog: pytest.LogCaptureFixture) -> None:
    settings = make_settings(
        TELEGRAM_BOT_TOKEN=f"not-a-token-{LEAK_MARKER}", TELEGRAM_CHANNEL_ID="@fhc"
    )
    with caplog.at_level(logging.DEBUG):
        app = create_app(settings, llm_provider=DownProvider())
    client = TestClient(app, base_url=BASE_URL, headers=AUTH)

    assert client.get("/health").status_code == 200
    response = client.get("/telegram/check")
    assert response.status_code == 200
    assert response.json()["status"] == "invalid_token"
    assert LEAK_MARKER not in response.text
    assert LEAK_MARKER not in caplog.text


def test_non_local_ollama_url_keeps_the_api_up(caplog: pytest.LogCaptureFixture) -> None:
    settings = make_settings(OLLAMA_BASE_URL="http://user:pw-secret@10.0.0.5:11434")
    with caplog.at_level(logging.DEBUG):
        app = create_app(settings)
    client = TestClient(app, base_url=BASE_URL, headers=AUTH)

    assert client.get("/health").status_code == 200
    body = client.get("/llm/check").json()
    assert body["health"]["status"] == "error"
    assert body["health"]["provider"] == "ollama"
    assert body["health"]["configured_model"] == settings.OLLAMA_MODEL
    assert "credentials" in body["health"]["message"]
    assert body["test"] is None
    for text in (str(body), caplog.text):
        assert "pw-secret" not in text
        assert "10.0.0.5" not in text


def test_remote_ollama_url_is_reported() -> None:
    app = create_app(make_settings(OLLAMA_BASE_URL="http://10.0.0.5:11434"))
    health = TestClient(app, base_url=BASE_URL, headers=AUTH).get("/llm/check").json()["health"]
    assert health["status"] == "error"
    assert "must point to localhost" in health["message"]


def test_misconfigured_provider_refuses_generation() -> None:
    provider = MisconfiguredProvider("ollama", "m", LLMConfigError("bad config"))
    with pytest.raises(LLMConfigError, match="bad config"):
        provider.generate_text(system="s", user="u", max_tokens=1)
    with pytest.raises(LLMConfigError, match="bad config"):
        provider.generate_structured(system="s", user="u", schema=ProviderHealth)


# --- shutdown -------------------------------------------------------------------------


def test_shutdown_closes_every_owned_client_even_when_one_close_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[str] = []

    def failing_close(self: OllamaProvider) -> None:
        closed.append("ollama")
        raise RuntimeError("close failed")

    def recording_close(self: TelegramClient) -> None:
        closed.append("telegram")

    monkeypatch.setattr(OllamaProvider, "close", failing_close)
    monkeypatch.setattr(TelegramClient, "close", recording_close)
    settings = make_settings(TELEGRAM_BOT_TOKEN=f"123456789:{LEAK_MARKER}")
    app = create_app(settings)

    with pytest.raises(RuntimeError, match="close failed"), TestClient(app, base_url=BASE_URL):
        pass

    assert sorted(closed) == ["ollama", "telegram"]
    assert app.state.pool.closed

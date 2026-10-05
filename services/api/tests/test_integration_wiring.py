"""The LLM and Telegram routers are mounted behind the token and wired to settings."""

from typing import TypeVar

from fastapi.testclient import TestClient
from pydantic import BaseModel

from fhc_api.llm.provider import ProviderHealth
from fhc_api.main import create_app

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

from fastapi import FastAPI
from fastapi.testclient import TestClient

from fhc_api.llm.provider import HealthStatus, LLMOutputError, LLMProvider, ProviderHealth, T
from fhc_api.llm.router import LLMCheckSample, build_llm_router


class FakeProvider:
    def __init__(self, status: HealthStatus = "ok", fail: bool = False) -> None:
        self.status = status
        self.fail = fail
        self.calls = 0

    @property
    def name(self) -> str:
        return "fake"

    def generate_structured(
        self, *, system: str, user: str, schema: type[T], temperature: float = 0.0
    ) -> T:
        self.calls += 1
        if self.fail:
            raise LLMOutputError("Model output did not match schema.")
        return schema.model_validate(
            {"event_name": "Fırat Hackathon", "city": "Elazığ", "year": 2026}
        )

    def generate_text(
        self, *, system: str, user: str, max_tokens: int, temperature: float = 0.0
    ) -> str:
        return ""

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider="fake",
            status=self.status,
            configured_model="m",
            installed_models=["m"] if self.status == "ok" else [],
            message=self.status,
        )


def client_for(provider: FakeProvider) -> TestClient:
    def get_provider() -> LLMProvider:
        return provider

    app = FastAPI()
    app.include_router(build_llm_router(get_provider))
    return TestClient(app)


def test_check_ok_runs_one_structured_call() -> None:
    provider = FakeProvider()

    response = client_for(provider).get("/llm/check")

    assert response.status_code == 200
    body = response.json()
    assert body["health"]["status"] == "ok"
    assert body["test"]["ok"] is True
    assert body["test"]["output"] == {
        "event_name": "Fırat Hackathon",
        "city": "Elazığ",
        "year": 2026,
    }
    assert isinstance(body["test"]["latency_ms"], int)
    assert provider.calls == 1


def test_check_not_running_skips_test_call() -> None:
    provider = FakeProvider(status="not_running")

    body = client_for(provider).get("/llm/check").json()

    assert body["health"]["status"] == "not_running"
    assert body["test"] is None
    assert provider.calls == 0


def test_check_model_missing() -> None:
    body = client_for(FakeProvider(status="model_missing")).get("/llm/check").json()
    assert body["health"]["status"] == "model_missing"
    assert body["test"] is None


def test_check_reports_output_error() -> None:
    body = client_for(FakeProvider(fail=True)).get("/llm/check").json()

    assert body["test"]["ok"] is False
    assert body["test"]["output"] is None
    assert "did not match" in body["test"]["error"]


def test_openapi_operation_id() -> None:
    schema = client_for(FakeProvider()).get("/openapi.json").json()
    assert schema["paths"]["/llm/check"]["get"]["operationId"] == "llm_check"


def test_sample_schema_has_three_fields() -> None:
    assert set(LLMCheckSample.model_fields) == {"event_name", "city", "year"}

"""Provider-neutral LLM interface (AI_ARCHITECTURE §2).

The interface is intentionally tiny and framework-free (D-10). V1 methods are synchronous:
FastAPI runs sync endpoints in its thread pool, and the admin API is single-user and local.
"""

from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)

HealthStatus = Literal["ok", "not_running", "model_missing", "error"]


class LLMError(Exception):
    """Base class for provider errors. Messages never contain secrets or prompt content."""


class LLMConfigError(LLMError, ValueError):
    """The provider was constructed with an unsafe or invalid configuration."""


class LLMUnavailableError(LLMError):
    """The provider cannot be reached (not running, connection refused, timeout)."""


class LLMTimeoutError(LLMUnavailableError):
    """The provider did not answer within the configured timeout."""


class LLMModelMissingError(LLMError):
    """The configured model is not installed on the provider."""


class LLMOutputError(LLMError):
    """The model output did not match the requested schema, even after one repair retry."""


class ProviderHealth(BaseModel):
    provider: str
    status: HealthStatus
    configured_model: str
    installed_models: list[str] = Field(default_factory=list)
    message: str


class LLMProvider(Protocol):
    @property
    def name(self) -> str: ...

    def generate_structured(
        self, *, system: str, user: str, schema: type[T], temperature: float = 0.0
    ) -> T:
        """Return a validated instance of `schema`; raise LLMOutputError after 1 repair retry."""
        ...

    def generate_text(
        self, *, system: str, user: str, max_tokens: int, temperature: float = 0.0
    ) -> str: ...

    def health(self) -> ProviderHealth: ...


class MisconfiguredProvider:
    """Stands in for a provider whose configuration was rejected at startup, so the API
    stays up: `health()` reports `error` with the (secret-free) configuration message and
    every generation call raises LLMConfigError."""

    def __init__(self, name: str, configured_model: str, error: LLMConfigError) -> None:
        self._name = name
        self._configured_model = configured_model
        self._message = str(error)

    @property
    def name(self) -> str:
        return self._name

    def generate_structured(
        self, *, system: str, user: str, schema: type[T], temperature: float = 0.0
    ) -> T:
        raise LLMConfigError(self._message)

    def generate_text(
        self, *, system: str, user: str, max_tokens: int, temperature: float = 0.0
    ) -> str:
        raise LLMConfigError(self._message)

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self._name,
            status="error",
            configured_model=self._configured_model,
            message=f"Configuration error: {self._message}",
        )

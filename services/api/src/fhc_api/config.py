"""Runtime settings, read from the environment and `services/api/.env`."""

from pathlib import Path
from typing import Annotated

from pydantic import AnyHttpUrl, Field, SecretStr, UrlConstraints
from pydantic_settings import BaseSettings, SettingsConfigDict

# src/fhc_api/config.py -> services/api/.env (independent of the working directory)
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

WebUrl = Annotated[AnyHttpUrl, UrlConstraints(allowed_schemes=["http", "https"])]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_ignore_empty=True,  # `WEB_BASE_URL=` means "not set"
        # The same .env holds settings for other modules (Ollama, Telegram).
        extra="ignore",
        frozen=True,
    )

    DATABASE_URL: SecretStr
    ADMIN_API_TOKEN: SecretStr = Field(min_length=32)
    # Revalidation of the public site is disabled unless both are set.
    WEB_BASE_URL: WebUrl | None = None
    WEB_REVALIDATE_SECRET: SecretStr | None = None
    ALLOWED_HOSTS: list[str] = Field(default_factory=lambda: ["127.0.0.1", "localhost"])

    # Local LLM (D-09). The model is a placeholder until the V1.2 benchmark picks one.
    OLLAMA_BASE_URL: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "qwen3.5:0.8b"
    # The first call after a model load can take ~50 s on the dev laptop.
    OLLAMA_TIMEOUT_S: float = Field(default=120.0, gt=0)

    # Telegram (D-12). The check reports `not_configured` while either is unset.
    TELEGRAM_BOT_TOKEN: SecretStr | None = None
    TELEGRAM_CHANNEL_ID: str | None = None

"""Runtime settings, read from the environment and `services/api/.env`."""

from pathlib import Path
from typing import Annotated

from pydantic import AnyHttpUrl, Field, SecretStr, UrlConstraints, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# src/fhc_api/config.py -> services/api/.env (independent of the working directory)
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

# The value shipped in `.env.example`; copying the file without editing it must fail.
ADMIN_TOKEN_PLACEHOLDER = "replace-with-a-random-token-of-at-least-32-characters"  # noqa: S105

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

    # Admin bot (V1.1b, D-21): a separate bot for review/application decisions. Kept as raw
    # strings and parsed by `fhc_api.admin_bot.settings`, so a bad value only disables the
    # bot (reported by GET /admin-bot/status) and never stops the API.
    TELEGRAM_ADMIN_ENABLED: str | None = None  # true/false, default false
    TELEGRAM_ADMIN_BOT_TOKEN: SecretStr | None = None
    TELEGRAM_ADMIN_USER_IDS: str | None = None  # numeric Telegram user ids, comma-separated
    TELEGRAM_ADMIN_MAX_PRESS_AGE_H: str | None = None  # default 12
    TELEGRAM_ADMIN_SCAN_INTERVAL_S: str | None = None  # default 60

    @field_validator("ADMIN_API_TOKEN")
    @classmethod
    def _not_the_placeholder(cls, value: SecretStr) -> SecretStr:
        if value.get_secret_value().strip() == ADMIN_TOKEN_PLACEHOLDER:
            raise ValueError(
                "ADMIN_API_TOKEN is still the .env.example placeholder; "
                "set a random token of at least 32 characters"
            )
        return value

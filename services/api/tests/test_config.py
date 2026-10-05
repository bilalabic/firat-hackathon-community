from pathlib import Path

import pytest
from pydantic import ValidationError

from fhc_api.config import ADMIN_TOKEN_PLACEHOLDER, ENV_FILE, Settings
from tests.conftest import make_settings


def test_defaults() -> None:
    settings = make_settings()

    assert settings.ALLOWED_HOSTS == ["127.0.0.1", "localhost"]
    assert settings.WEB_BASE_URL is None
    assert settings.WEB_REVALIDATE_SECRET is None


def test_short_admin_token_is_rejected() -> None:
    with pytest.raises(ValidationError, match="ADMIN_API_TOKEN"):
        make_settings(ADMIN_API_TOKEN="x" * 31)


def test_env_example_placeholder_token_is_rejected() -> None:
    example = (ENV_FILE.parent / ".env.example").read_text(encoding="utf-8")
    assert f"ADMIN_API_TOKEN={ADMIN_TOKEN_PLACEHOLDER}\n" in example

    with pytest.raises(ValidationError, match=r"still the \.env\.example placeholder"):
        make_settings(ADMIN_API_TOKEN=ADMIN_TOKEN_PLACEHOLDER)


def test_web_base_url_must_be_http() -> None:
    with pytest.raises(ValidationError):
        make_settings(WEB_BASE_URL="ftp://example.com")


def test_secrets_are_not_shown_in_repr() -> None:
    settings = make_settings(WEB_REVALIDATE_SECRET="very-secret-value")

    assert "very-secret-value" not in repr(settings)
    assert "admin_backend_local_dev" not in repr(
        make_settings(DATABASE_URL="postgresql://u:admin_backend_local_dev@h/db")
    )


def test_env_file_empty_values_mean_unset_and_unknown_keys_are_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DATABASE_URL=postgresql://u:p@127.0.0.1:54322/postgres\n"
        f"ADMIN_API_TOKEN={'t' * 32}\n"
        "WEB_BASE_URL=\n"
        "WEB_REVALIDATE_SECRET=\n"
        "OLLAMA_BASE_URL=http://127.0.0.1:11434\n",
        encoding="utf-8",
    )
    for name in ("DATABASE_URL", "ADMIN_API_TOKEN", "WEB_BASE_URL", "WEB_REVALIDATE_SECRET"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=env_file)  # type: ignore[call-arg]

    assert settings.WEB_BASE_URL is None
    assert settings.ADMIN_API_TOKEN.get_secret_value() == "t" * 32

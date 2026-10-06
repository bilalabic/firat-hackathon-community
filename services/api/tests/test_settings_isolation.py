"""Tests must never pick up values from the developer's real `.env` or environment."""

from pathlib import Path

import pytest

from fhc_api import config

from .conftest import make_settings


def test_make_settings_ignores_the_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "TELEGRAM_ADMIN_ENABLED=true\n"
        "TELEGRAM_ADMIN_BOT_TOKEN=123456789:LeakedFromDotEnvNotForTests_000\n"
        "DATABASE_URL=postgresql://prod@db.example.com:5432/postgres\n",
        encoding="utf-8",
    )
    monkeypatch.setitem(config.Settings.model_config, "env_file", env)

    settings = make_settings()

    assert settings.TELEGRAM_ADMIN_ENABLED is None
    assert settings.TELEGRAM_ADMIN_BOT_TOKEN is None
    assert "example.com" not in settings.DATABASE_URL.get_secret_value()


def test_settings_env_vars_are_cleared_for_every_test() -> None:
    import os

    leaked = [name for name in config.Settings.model_fields if name in os.environ]
    assert leaked == []

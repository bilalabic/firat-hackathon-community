"""Shared fixtures.

Integration tests run against the LOCAL Supabase Postgres as `admin_backend`. Each test
runs inside one transaction that is always rolled back, and each request gets its own
savepoint (mirroring autocommit statements in production), so no rows are left behind.
The URL comes from TEST_DATABASE_URL or the documented local default; `.env` is never
read here, so tests cannot reach a cloud database by accident.
"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlsplit

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from fhc_api.config import Settings
from fhc_api.db import Conn, get_conn, get_conn_factory
from fhc_api.main import create_app
from fhc_api.review.signals import UrlCheck

LOCAL_DATABASE_URL = "postgresql://admin_backend:admin_backend_local_dev@127.0.0.1:54322/postgres"
TOKEN = "test-token-" + "x" * 32
AUTH = {"Authorization": f"Bearer {TOKEN}"}
BASE_URL = "http://127.0.0.1"
# Every row created by tests carries this prefix (leftover checks search for it).
MARK = "Pytest M3"


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "DATABASE_URL": "postgresql://unused@127.0.0.1:1/unused",
        "ADMIN_API_TOKEN": TOKEN,
        **overrides,
    }
    # `_env_file=None` disables services/api/.env: it may hold real tokens (and, on the dev
    # laptop, the production DSN). Note that `Settings.model_validate` would still read it.
    # Settings-named environment variables are cleared by `_isolate_settings_env` below.
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


@pytest.fixture(autouse=True)
def _isolate_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """No Settings field can come from the developer's real environment."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name, raising=False)


class RecordingRevalidator:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def revalidate(self, tags: list[str]) -> None:
        self.calls.append(tags)


class FakeUrlChecker:
    def __init__(self, result: UrlCheck | None = None) -> None:
        self.result = result or UrlCheck(reachable=True, detail="HTTP 200")
        self.urls: list[str] = []

    def __call__(self, url: str) -> UrlCheck:
        self.urls.append(url)
        return self.result


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture(scope="session")
def _db_connection() -> Iterator[Conn]:
    url = os.environ.get("TEST_DATABASE_URL", LOCAL_DATABASE_URL)
    host = urlsplit(url).hostname
    if host not in ("127.0.0.1", "localhost"):
        pytest.fail(f"integration tests only run against a local database, not {host!r}")
    try:
        conn = psycopg.connect(url, autocommit=True, row_factory=dict_row, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("local Supabase Postgres is not running (pnpm db:start)")
    with conn:
        yield conn


@pytest.fixture
def db(_db_connection: Conn) -> Iterator[Conn]:
    """A connection inside a transaction that is rolled back after the test."""
    with _db_connection.transaction(force_rollback=True):
        yield _db_connection


@pytest.fixture
def revalidator() -> RecordingRevalidator:
    return RecordingRevalidator()


@pytest.fixture
def url_checker() -> FakeUrlChecker:
    return FakeUrlChecker()


@pytest.fixture
def app(
    settings: Settings, revalidator: RecordingRevalidator, url_checker: FakeUrlChecker
) -> FastAPI:
    return create_app(settings, revalidator=revalidator, url_checker=url_checker)


@pytest.fixture
def client(app: FastAPI, db: Conn) -> TestClient:
    def conn_in_savepoint() -> Iterator[Conn]:
        with db.transaction():
            yield db

    app.dependency_overrides[get_conn] = conn_in_savepoint
    app.dependency_overrides[get_conn_factory] = lambda: contextmanager(conn_in_savepoint)
    return TestClient(app, base_url=BASE_URL, headers=AUTH)


@pytest.fixture
def anon_client(app: FastAPI) -> TestClient:
    """No token and no database: for auth and host checks."""
    return TestClient(app, base_url=BASE_URL)

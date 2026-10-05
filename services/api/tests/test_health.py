from collections.abc import Iterator

import psycopg
from fastapi.testclient import TestClient

from fhc_api.db import Conn, get_conn
from fhc_api.main import create_app
from tests.conftest import AUTH, BASE_URL, make_settings


def test_health_returns_ok_without_a_database() -> None:
    # Lifespan runs (context manager) and opens the pool in the background; the
    # unreachable database must not prevent startup or /health.
    app = create_app(make_settings())
    with TestClient(app, base_url=BASE_URL) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "api"}


def test_database_outage_is_503_without_details() -> None:
    app = create_app(make_settings())

    def unavailable() -> Iterator[Conn]:
        raise psycopg.OperationalError("connection to server failed: secret details")
        yield  # pragma: no cover

    app.dependency_overrides[get_conn] = unavailable
    response = TestClient(app, base_url=BASE_URL, headers=AUTH).get("/system/db")

    assert response.status_code == 503
    assert response.json() == {"detail": "database unavailable"}

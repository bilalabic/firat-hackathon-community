"""MVP criterion 7: no token -> 401, foreign Host -> 400; /health stays open."""

import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import AUTH, BASE_URL, TOKEN


def _protected_routes(app: FastAPI) -> list[tuple[str, str]]:
    """Every documented operation except /health, plus the schema route itself."""
    routes = [("GET", "/openapi.json")]
    for path, path_item in app.openapi()["paths"].items():
        if path != "/health":
            # Any syntactically valid id works: auth is checked before the handler runs.
            concrete = re.sub(r"\{[^}]+\}", "00000000-0000-0000-0000-000000000000", path)
            routes.extend((method.upper(), concrete) for method in path_item)
    return routes


def test_health_is_open(anon_client: TestClient) -> None:
    response = anon_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "api"}


def test_every_other_route_requires_the_token(app: FastAPI, anon_client: TestClient) -> None:
    routes = _protected_routes(app)
    assert len(routes) >= 15  # guards against the route discovery silently finding nothing

    for method, path in routes:
        response = anon_client.request(method, path)
        assert response.status_code == 401, (method, path)
        assert response.json() == {"detail": "invalid or missing bearer token"}
        assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "authorization",
    [
        "Bearer wrong-token-" + "x" * 32,
        f"Bearer {TOKEN}x",
        f"Bearer {TOKEN[:-1]}",
        f"Basic {TOKEN}",
        TOKEN,
        "Bearer ",
    ],
)
def test_wrong_token_is_rejected(anon_client: TestClient, authorization: str) -> None:
    response = anon_client.get("/overview", headers={"Authorization": authorization})

    assert response.status_code == 401


@pytest.mark.parametrize("host", ["evil.example", "127.0.0.1.nip.io", "localhost.evil.example"])
def test_foreign_host_header_is_rejected(anon_client: TestClient, host: str) -> None:
    # DNS rebinding: the request reaches 127.0.0.1 but carries the attacker's host name.
    for path in ("/health", "/events"):
        response = anon_client.get(path, headers={**AUTH, "Host": host})
        assert response.status_code == 400, (host, path)


def test_allowed_hosts_accept_port_suffix(anon_client: TestClient) -> None:
    for host in ("127.0.0.1:8100", "localhost:8000"):
        assert anon_client.get("/health", headers={"Host": host}).status_code == 200


def test_no_cors_headers(anon_client: TestClient) -> None:
    response = anon_client.options(
        "/events",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )

    assert "access-control-allow-origin" not in response.headers


def test_docs_are_not_served(anon_client: TestClient) -> None:
    for path in ("/docs", "/redoc"):
        assert anon_client.get(path, headers=AUTH).status_code == 404


def test_openapi_requires_token_and_has_explicit_operation_ids(app: FastAPI) -> None:
    client = TestClient(app, base_url=BASE_URL)
    assert client.get("/openapi.json").status_code == 401

    schema = client.get("/openapi.json", headers=AUTH).json()

    operation_ids = [
        operation["operationId"]
        for path_item in schema["paths"].values()
        for operation in path_item.values()
    ]
    assert len(operation_ids) == len(set(operation_ids))
    # snake_case ids chosen by hand, never FastAPI's generated "<name>_<path>_<method>".
    assert all(re.fullmatch(r"[a-z]+(_[a-z]+)*", op) for op in operation_ids), operation_ids
    assert {"list_events", "transition_event", "get_event_review", "get_overview"} <= set(
        operation_ids
    )
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if path != "/health":
                assert operation.get("security") == [{"HTTPBearer": []}], (method, path)
                assert "401" in operation["responses"], (method, path)
    names = set(schema["components"]["schemas"])
    assert {"EventPage", "CommunityApplicationPage", "TeamApplicationPage"} <= names
    assert not any(name.startswith("Page") for name in names)

"""Community and team applications (MVP criterion 10). Rows are inserted directly
(the public form RPCs are tested by pgTAP) inside the rolled-back test transaction."""

import logging

import pytest
from fastapi.testclient import TestClient

from fhc_api.community import repository
from fhc_api.db import Conn
from tests.conftest import MARK
from tests.factories import insert_community_application, insert_team_application

UNKNOWN = "00000000-0000-0000-0000-000000000000"


@pytest.mark.parametrize(
    ("path", "insert"),
    [
        ("/community-applications", insert_community_application),
        ("/team-applications", insert_team_application),
    ],
)
def test_list_filter_and_update_status(
    client: TestClient, db: Conn, path: str, insert: object, caplog: pytest.LogCaptureFixture
) -> None:
    assert callable(insert)
    new = insert(db)
    contacted = insert(db, status="contacted")

    with caplog.at_level(logging.DEBUG):
        listing = client.get(path, params={"status": "new", "limit": 200}).json()
        updated = client.patch(f"{path}/{new['id']}", json={"status": "accepted"})

    ids = {item["id"] for item in listing["items"]}
    assert str(new["id"]) in ids
    assert str(contacted["id"]) not in ids
    assert all(item["status"] == "new" for item in listing["items"])
    assert updated.status_code == 200
    assert updated.json()["status"] == "accepted"
    assert updated.json()["full_name"] == new["full_name"]
    # Personal data is never logged.
    assert new["full_name"] not in caplog.text


@pytest.mark.parametrize("path", ["/community-applications", "/team-applications"])
def test_update_errors(client: TestClient, path: str) -> None:
    assert client.patch(f"{path}/{UNKNOWN}", json={"status": "spam"}).status_code == 404
    assert client.patch(f"{path}/{UNKNOWN}", json={"status": "deleted"}).status_code == 422
    assert (
        client.patch(f"{path}/{UNKNOWN}", json={"status": "new", "full_name": "x"}).status_code
        == 422
    )
    assert client.get(path, params={"status": "bogus"}).status_code == 422


def test_community_application_fields(client: TestClient, db: Conn) -> None:
    row = insert_community_application(
        db, preferred_channel="whatsapp", telegram_username=None, phone="+905551112233"
    )

    items = client.get("/community-applications", params={"limit": 200}).json()["items"]
    item = next(i for i in items if i["id"] == str(row["id"]))

    assert item["preferred_channel"] == "whatsapp"
    assert item["phone"] == "+905551112233"
    assert item["interests"] == []


def test_invalid_row_is_a_generic_500_without_personal_data_in_logs(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # A row the response model rejects (a server bug, e.g. schema drift) must not echo
    # its values in the response or in the log.
    secret_name, secret_phone = f"{MARK} Private Person", "+905559998877"
    row = {"full_name": secret_name, "phone": secret_phone, "preferred_channel": "sms"}
    monkeypatch.setattr(repository, "list_page", lambda *args, **kwargs: ([row], 1))

    with caplog.at_level(logging.DEBUG):
        response = client.get("/community-applications")

    assert response.status_code == 500
    assert response.json() == {"detail": "internal error"}
    assert "internal validation error on GET /community-applications" in caplog.text
    assert "literal_error at preferred_channel" in caplog.text
    assert "missing at id" in caplog.text
    for value in (secret_name, secret_phone, "sms"):
        assert value not in caplog.text
        assert value not in response.text

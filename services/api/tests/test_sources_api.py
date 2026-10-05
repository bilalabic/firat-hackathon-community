from fastapi.testclient import TestClient

from tests.conftest import MARK
from tests.factories import create_event

UNKNOWN = "00000000-0000-0000-0000-000000000000"


def test_seeded_sources_are_listed(client: TestClient) -> None:
    names = {source["name"] for source in client.get("/sources").json()}

    assert {"Manual entry", "Devpost", "Patika.dev"} <= names


def test_create_and_update_source(client: TestClient) -> None:
    created = client.post(
        "/sources",
        json={"name": f"{MARK} Source", "kind": "university", "tier": 1, "base_url": ""},
    )
    assert created.status_code == 201
    source = created.json()
    assert source["base_url"] is None
    assert source["retrieval_method"] == "manual"
    assert source["enabled"] is True

    updated = client.patch(f"/sources/{source['id']}", json={"enabled": False, "notes": "Paused"})
    unchanged = client.patch(f"/sources/{source['id']}", json={})

    assert updated.status_code == 200
    assert updated.json()["enabled"] is False
    assert updated.json()["notes"] == "Paused"
    assert unchanged.json()["notes"] == "Paused"


def test_source_validation_and_conflicts(client: TestClient) -> None:
    duplicate = client.post(
        "/sources", json={"name": "Devpost", "kind": "event_platform", "tier": 2}
    )
    bad_tier = client.post("/sources", json={"name": f"{MARK} X", "kind": "manual", "tier": 5})
    bad_kind = client.post("/sources", json={"name": f"{MARK} X", "kind": "blog", "tier": 1})

    assert duplicate.status_code == 409
    assert duplicate.json() == {"detail": "conflicts with an existing row (sources_name_key)"}
    assert bad_tier.status_code == 422
    assert bad_kind.status_code == 422
    assert client.patch(f"/sources/{UNKNOWN}", json={"enabled": False}).status_code == 404


def test_event_sources_add_list_remove(client: TestClient) -> None:
    event = create_event(client)
    devpost = next(s for s in client.get("/sources").json() if s["name"] == "Devpost")
    base = f"/events/{event['id']}/sources"

    added = client.post(
        base,
        json={
            "url": "https://WWW.devpost.com/hackathons/pytest-m3/?utm_medium=x",
            "role": "announcement",
            "source_id": devpost["id"],
        },
    )
    assert added.status_code == 201, added.text
    item = added.json()
    assert item["url_normalized"] == "devpost.com/hackathons/pytest-m3"
    assert item["source_name"] == "Devpost"
    assert item["source_tier"] == 2

    # Same page, different spelling -> the same normalized URL -> conflict.
    again = client.post(
        base, json={"url": "https://devpost.com/hackathons/pytest-m3", "role": "official"}
    )
    assert again.status_code == 409

    assert [row["id"] for row in client.get(base).json()] == [item["id"]]
    assert client.delete(f"{base}/{item['id']}").status_code == 204
    assert client.get(base).json() == []
    assert client.delete(f"{base}/{item['id']}").status_code == 404


def test_event_sources_errors(client: TestClient) -> None:
    event = create_event(client)
    base = f"/events/{event['id']}/sources"

    assert client.get(f"/events/{UNKNOWN}/sources").status_code == 404
    assert (
        client.post(
            f"/events/{UNKNOWN}/sources", json={"url": "https://a.example", "role": "official"}
        ).status_code
        == 404
    )
    unknown_source = client.post(
        base, json={"url": "https://a.example", "role": "official", "source_id": UNKNOWN}
    )
    assert unknown_source.status_code == 422
    assert "referenced row does not exist" in unknown_source.json()["detail"]
    assert client.post(base, json={"url": "ftp://a.example", "role": "official"}).status_code == 422
    assert client.post(base, json={"url": "https://a.example", "role": "rumour"}).status_code == 422


def test_removing_an_event_source_of_another_event_is_404(client: TestClient) -> None:
    first, second = create_event(client), create_event(client)
    item = client.post(
        f"/events/{first['id']}/sources", json={"url": "https://a.example/x", "role": "official"}
    ).json()

    assert client.delete(f"/events/{second['id']}/sources/{item['id']}").status_code == 404
    assert len(client.get(f"/events/{first['id']}/sources").json()) == 1

"""URL import (V1.2) through the API, against the local database (rolled back) with a fake
page loader and extractor. Never fetches a page or calls an LLM."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fhc_api.db import Conn, get_conn, get_conn_factory
from fhc_api.importing.models import (
    ExtractableField,
    ExtractionResult,
    FieldFlag,
    FieldProposal,
    PageContent,
    PageError,
    StructuredValue,
)
from fhc_api.importing.service import (
    choose_official_url,
    clean_title,
    matches_current,
    value_text,
)
from fhc_api.main import create_app
from tests.conftest import AUTH, BASE_URL, MARK, FakeUrlChecker, RecordingRevalidator, make_settings
from tests.factories import create_event

URL = "https://pytest-import.example.com/hackathon"
FETCHED_AT = datetime(2026, 10, 11, 9, 30, tzinfo=UTC)


def make_page(url: str = URL, **overrides: Any) -> PageContent:
    values: dict[str, Any] = {
        "requested_url": url,
        "final_url": url,
        "fetched_at": FETCHED_AT,
        "title": f"{MARK} Import Hackathon | Example",
        "text": "Pytest Import Hackathon, 1-2 November 2026, Elazığ.",
        "structured": {
            "start_date": StructuredValue(date(2026, 11, 1), "jsonld", '"startDate": "2026-11-01"')
        },
        "image_url": "https://pytest-import.example.com/og.png",
        **overrides,
    }
    return PageContent(**values)


def proposal(field: ExtractableField, value: Any, source: str = "llm") -> FieldProposal:
    return FieldProposal(field, value, source, f"snippet for {field}")  # type: ignore[arg-type]


def full_result(page: PageContent) -> ExtractionResult:
    return ExtractionResult(
        page=page,
        fields={
            "title": proposal("title", f"{MARK} Import Hackathon"),
            "start_date": proposal("start_date", date(2026, 11, 1), "jsonld"),
            "end_date": proposal("end_date", date(2026, 11, 2)),
            "city": proposal("city", "Elazığ"),
            "country": proposal("country", "TR"),
            "team_min": proposal("team_min", 2),
            "team_max": proposal("team_max", 4),
            "prize_pool": proposal("prize_pool", Decimal("50000")),
            "currency": proposal("currency", "TRY"),
            "is_free": proposal("is_free", True),
            "format": proposal("format", "in_person", "meta"),
        },
        flags=[
            FieldFlag("start_date", "conflict", "The LLM proposed 2026-11-02; JSON-LD kept."),
            FieldFlag("organizer", "unsupported", "The snippet does not occur in the page."),
        ],
        extracted_by="llm:test-model",
        llm_error=None,
        llm_duration_ms=1234,
    )


class FakeLoader:
    def __init__(self) -> None:
        self.urls: list[str] = []
        self.page: Callable[[str], PageContent] = make_page
        self.error: Exception | None = None

    def load_page(self, url: str) -> PageContent:
        self.urls.append(url)
        if self.error is not None:
            raise self.error
        return self.page(url)


class FakeExtractor:
    def __init__(self) -> None:
        self.calls = 0
        self.result: Callable[[PageContent], ExtractionResult] = full_result
        self.error: Exception | None = None

    def extract(self, page: PageContent) -> ExtractionResult:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result(page)


def make_client(app: FastAPI, db: Conn) -> TestClient:
    def conn_in_savepoint() -> Iterator[Conn]:
        with db.transaction():
            yield db

    app.dependency_overrides[get_conn] = conn_in_savepoint
    app.dependency_overrides[get_conn_factory] = lambda: contextmanager(conn_in_savepoint)
    return TestClient(app, base_url=BASE_URL, headers=AUTH)


@pytest.fixture
def loader() -> FakeLoader:
    return FakeLoader()


@pytest.fixture
def extractor() -> FakeExtractor:
    return FakeExtractor()


@pytest.fixture
def importer_app(
    loader: FakeLoader, extractor: FakeExtractor, revalidator: RecordingRevalidator
) -> FastAPI:
    return create_app(
        make_settings(),
        revalidator=revalidator,
        url_checker=FakeUrlChecker(),
        page_loader=loader,
        extractor=extractor,
    )


@pytest.fixture
def api(importer_app: FastAPI, db: Conn) -> TestClient:
    return make_client(importer_app, db)


def do_import(api: TestClient, url: str = URL) -> dict[str, Any]:
    response = api.post("/imports/url", json={"url": url})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def runs(db: Conn) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in db.execute(
            "select * from app.runs where input->>'url' like 'https://pytest-import.%%'"
            " order by started_at"
        ).fetchall()
    ]


# --- availability and input -----------------------------------------------------------


def test_import_routes_require_the_token(anon_client: TestClient) -> None:
    assert anon_client.post("/imports/url", json={"url": URL}).status_code == 401
    assert anon_client.get("/imports/runs").status_code == 401
    assert (
        anon_client.get(f"/events/{'0' * 8}-0000-0000-0000-{'0' * 12}/evidence").status_code == 401
    )


def test_import_is_not_available_without_loader_and_extractor(client: TestClient) -> None:
    response = client.post("/imports/url", json={"url": URL})
    assert response.status_code == 409
    assert response.json()["detail"].startswith("URL import is not available")
    # Reads still work.
    assert client.get("/imports/runs").status_code == 200


@pytest.mark.parametrize(
    "url", ["ftp://pytest-import.example.com/x", "not a url", "https://user:pw@example.com/"]
)
def test_invalid_urls_are_rejected_by_validation(
    api: TestClient, loader: FakeLoader, url: str
) -> None:
    assert api.post("/imports/url", json={"url": url}).status_code == 422
    assert loader.urls == []


def test_private_hosts_are_rejected_without_a_run(
    api: TestClient, db: Conn, loader: FakeLoader
) -> None:
    response = api.post("/imports/url", json={"url": "http://localhost:8080/admin"})
    assert response.status_code == 422
    assert "url" in response.json()["detail"]
    assert loader.urls == []
    assert db.execute(
        "select count(*) as n from app.runs where input->>'url' like '%%localhost%%'"
    ).fetchone() == {"n": 0}


# --- duplicates -----------------------------------------------------------------------


def test_exact_duplicate_returns_the_existing_event_without_fetching(
    api: TestClient, db: Conn, loader: FakeLoader
) -> None:
    event = create_event(api, official_url=URL)
    body = do_import(api, "https://www.pytest-import.example.com/hackathon/?utm_source=x")
    assert body == {"outcome": "duplicate", "event_id": event["id"], "run": None}
    assert loader.urls == []
    assert runs(db) == []


def test_duplicate_found_after_a_redirect(api: TestClient, db: Conn, loader: FakeLoader) -> None:
    existing = create_event(api, official_url="https://pytest-import.example.com/2026")
    loader.page = lambda url: make_page(url, final_url="https://pytest-import.example.com/2026")
    body = do_import(api, "https://pytest-import.example.com/hackathon")
    assert body["outcome"] == "duplicate"
    assert body["event_id"] == existing["id"]
    assert body["run"]["status"] == "succeeded"
    assert body["run"]["stats"]["outcome"] == "duplicate"
    assert db.execute(
        "select count(*) as n from app.events where title like %s", (f"{MARK} Import%",)
    ).fetchone() == {"n": 0}


# --- success --------------------------------------------------------------------------


def test_import_creates_a_draft_with_evidence(
    api: TestClient, db: Conn, loader: FakeLoader, revalidator: RecordingRevalidator
) -> None:
    body = do_import(api)
    assert body["outcome"] == "created"
    assert loader.urls == [URL]
    event_id = body["event_id"]

    event = api.get(f"/events/{event_id}").json()
    assert event["status"] == "draft"
    assert event["verification_status"] == "unverified"
    assert event["title"] == f"{MARK} Import Hackathon"
    assert event["official_url"] == URL
    assert event["start_date"] == "2026-11-01"
    assert event["city"] == "Elazığ"
    assert (event["team_min"], event["team_max"]) == (2, 4)
    assert event["prize_pool"] == "50000.00"
    assert event["is_free"] is True
    assert event["discovered_at"] is not None
    assert revalidator.calls == []  # a draft is not public

    sources = api.get(f"/events/{event_id}/sources").json()
    assert [(s["role"], s["source_name"], s["url"]) for s in sources] == [
        ("official", "Manual entry", URL)
    ]

    run = body["run"]
    assert run["status"] == "succeeded"
    assert run["url"] == URL
    assert run["event_id"] == event_id
    stats = run["stats"]
    assert stats["fields"] == 11
    assert stats["flags"] == 2
    assert stats["fields_by_source"] == {"llm": 9, "jsonld": 1, "meta": 1}
    assert stats["flags_by_kind"] == {"conflict": 1, "unsupported": 1}
    assert stats["extracted_by"] == "llm:test-model"
    assert stats["llm_ms"] == 1234
    assert stats["image_url"] == "https://pytest-import.example.com/og.png"
    assert {"page_ms", "extract_ms", "total_ms"} <= stats.keys()

    evidence = api.get(f"/events/{event_id}/evidence").json()
    assert evidence["run"]["id"] == run["id"]
    by_field = {item["field"]: item for item in evidence["fields"]}
    assert [item["field"] for item in evidence["fields"]][:3] == ["title", "organizer", "format"]
    assert by_field["start_date"]["source"] == "jsonld"
    assert by_field["start_date"]["extracted_by"] == "jsonld"
    assert by_field["start_date"]["value_text"] == "2026-11-01"
    assert by_field["start_date"]["flags"] == [
        {"kind": "conflict", "detail": "The LLM proposed 2026-11-02; JSON-LD kept."}
    ]
    assert by_field["start_date"]["matches_current"] is True
    assert by_field["city"]["extracted_by"] == "llm:test-model"
    assert by_field["city"]["snippet"] == "snippet for city"
    assert by_field["prize_pool"]["value_text"] == "50000"
    assert by_field["prize_pool"]["matches_current"] is True
    assert by_field["is_free"]["value_text"] == "true"
    assert by_field["organizer"] == {
        "field": "organizer",
        "value_text": None,
        "source": None,
        "extracted_by": None,
        "snippet": None,
        "flags": [{"kind": "unsupported", "detail": "The snippet does not occur in the page."}],
        "matches_current": None,
    }

    rows = db.execute(
        "select event_source_id from app.event_field_evidence where event_id = %s", (event_id,)
    ).fetchall()
    assert len(rows) == 13
    assert {str(row["event_source_id"]) for row in rows} == {sources[0]["id"]}

    audit = db.execute(
        "select actor, action, detail from app.admin_actions where entity_id = %s", (event_id,)
    ).fetchall()
    assert [(a["actor"], a["action"]) for a in audit] == [("admin_ui", "url_import")]
    assert audit[0]["detail"] == {"run_id": run["id"], "fields": 11, "flags": 2, "llm": True}

    listed = api.get("/imports/runs", params={"limit": 5}).json()
    assert listed["items"][0]["id"] == run["id"]
    assert listed["limit"] == 5


def test_evidence_tracks_later_edits(api: TestClient) -> None:
    event_id = do_import(api)["event_id"]
    assert api.patch(f"/events/{event_id}", json={"city": "Malatya"}).status_code == 200
    by_field = {f["field"]: f for f in api.get(f"/events/{event_id}/evidence").json()["fields"]}
    assert by_field["city"]["matches_current"] is False
    assert by_field["country"]["matches_current"] is True


def test_llm_error_still_creates_a_draft_from_structured_fields(
    api: TestClient, extractor: FakeExtractor
) -> None:
    def structured_only(page: PageContent) -> ExtractionResult:
        return ExtractionResult(
            page=page,
            fields={"start_date": proposal("start_date", date(2026, 11, 1), "jsonld")},
            flags=[],
            extracted_by=None,
            llm_error="Ollama is not running",
            llm_duration_ms=None,
        )

    extractor.result = structured_only
    body = do_import(api)
    assert body["outcome"] == "created"
    assert body["run"]["stats"]["llm_error"] == "Ollama is not running"
    assert body["run"]["stats"]["extracted_by"] is None
    event = api.get(f"/events/{body['event_id']}").json()
    # No title proposal: the page title is used and recorded as meta evidence.
    assert event["title"] == f"{MARK} Import Hackathon | Example"
    assert event["start_date"] == "2026-11-01"
    assert event["city"] is None
    fields = api.get(f"/events/{body['event_id']}/evidence").json()["fields"]
    assert [(f["field"], f["source"]) for f in fields] == [
        ("title", "meta"),
        ("start_date", "jsonld"),
    ]


def test_title_falls_back_to_the_host(
    api: TestClient, loader: FakeLoader, extractor: FakeExtractor
) -> None:
    loader.page = lambda url: make_page(url, title=None)
    extractor.result = lambda page: replace(full_result(page), fields={})
    event_id = do_import(api)["event_id"]
    assert api.get(f"/events/{event_id}").json()["title"] == (
        "Imported from pytest-import.example.com"
    )
    fields = api.get(f"/events/{event_id}/evidence").json()["fields"]
    assert all(f["value_text"] is None for f in fields)  # flags only


def test_values_failing_the_event_rules_are_dropped_and_flagged(
    api: TestClient, extractor: FakeExtractor
) -> None:
    def bad(page: PageContent) -> ExtractionResult:
        result = full_result(page)
        fields = {
            **result.fields,
            "country": proposal("country", "Turkey"),
            "team_min": proposal("team_min", 5),
            "team_max": proposal("team_max", 2),
            "end_date": proposal("end_date", date(2026, 10, 1)),
        }
        return replace(result, fields=fields, flags=[])

    extractor.result = bad
    body = do_import(api)
    event = api.get(f"/events/{body['event_id']}").json()
    assert event["country"] is None
    assert (event["team_min"], event["team_max"]) == (5, None)
    assert event["end_date"] is None
    flags = {
        f["field"]: [flag["kind"] for flag in f["flags"]]
        for f in api.get(f"/events/{body['event_id']}/evidence").json()["fields"]
        if f["flags"]
    }
    assert flags == {
        "country": ["invalid"],
        "end_date": ["rule_violation"],
        "team_max": ["rule_violation"],
    }


@pytest.mark.parametrize(
    ("final_url", "official_url"),
    [
        (
            "https://www.pytest-import.example.com/hackathon/en",
            "https://www.pytest-import.example.com/hackathon/en",
        ),
        ("https://other.example.org/hackathon", URL),
    ],
)
def test_official_url_follows_same_site_redirects_only(
    api: TestClient, loader: FakeLoader, final_url: str, official_url: str
) -> None:
    loader.page = lambda url: make_page(url, final_url=final_url)
    body = do_import(api)
    assert api.get(f"/events/{body['event_id']}").json()["official_url"] == official_url
    assert body["run"]["stats"]["final_url"] == final_url


# --- failures -------------------------------------------------------------------------


def test_page_error_fails_the_run_with_its_message(
    api: TestClient, db: Conn, loader: FakeLoader, extractor: FakeExtractor
) -> None:
    loader.error = PageError("The page has no readable content (it may need JavaScript).")
    response = api.post("/imports/url", json={"url": URL})
    assert response.status_code == 422
    assert response.json() == {
        "detail": "The page has no readable content (it may need JavaScript)."
    }
    assert extractor.calls == 0
    [run] = runs(db)
    assert run["status"] == "failed"
    assert run["error"] == "The page has no readable content (it may need JavaScript)."
    assert run["event_id"] is None
    assert run["finished_at"] is not None
    assert "page_ms" in run["stats"]


def test_unexpected_extractor_error_fails_the_run(
    importer_app: FastAPI, db: Conn, extractor: FakeExtractor
) -> None:
    extractor.error = RuntimeError("boom")
    api = make_client(importer_app, db)
    with pytest.raises(RuntimeError, match="boom"):
        api.post("/imports/url", json={"url": URL})
    [run] = runs(db)
    assert run["status"] == "failed"
    assert run["error"] == "internal error during the import (see the API log)"
    assert db.execute(
        "select count(*) as n from app.events where official_url = %s", (URL,)
    ).fetchone() == {"n": 0}


# --- evidence reads -------------------------------------------------------------------


def test_evidence_of_a_manual_event_is_empty(api: TestClient) -> None:
    event = create_event(api)
    assert api.get(f"/events/{event['id']}/evidence").json() == {
        "event_id": event["id"],
        "run": None,
        "extracted_at": None,
        "fields": [],
    }


def test_evidence_of_an_unknown_event_is_404(api: TestClient) -> None:
    response = api.get("/events/00000000-0000-0000-0000-000000000000/evidence")
    assert response.status_code == 404


def test_evidence_shows_the_latest_import_only(api: TestClient, db: Conn) -> None:
    event_id = do_import(api)["event_id"]
    # A second import of the same page is a duplicate; simulate an older run instead.
    db.execute(
        "insert into app.event_field_evidence (event_id, field, value_text, source,"
        " extracted_at) values (%s, 'venue', 'Old hall', 'llm', now() - interval '1 day')",
        (event_id,),
    )
    fields = api.get(f"/events/{event_id}/evidence").json()["fields"]
    assert "venue" not in {f["field"] for f in fields}


# --- pure helpers ---------------------------------------------------------------------


def test_value_text() -> None:
    assert value_text(True) == "true"
    assert value_text(date(2026, 1, 2)) == "2026-01-02"
    assert value_text(Decimal("1000.50")) == "1000.5"
    assert value_text(Decimal("1E+3")) == "1000"
    assert value_text(3) == "3"


def test_choose_official_url() -> None:
    assert choose_official_url(URL, URL) == URL
    assert choose_official_url("http://example.com/a", "https://www.example.com/a/") == (
        "https://www.example.com/a/"
    )
    assert choose_official_url("https://bit.ly/x", "https://example.com/a") == "https://bit.ly/x"
    assert choose_official_url(URL, URL + "/" + "x" * 600) == URL


def test_clean_title() -> None:
    assert clean_title("  A \n b  ") == "A b"
    assert clean_title("ab") is None
    assert clean_title(None) is None
    long = clean_title("x" * 300)
    assert long is not None and len(long) == 160 and long.endswith("…")


def test_matches_current() -> None:
    event = {"prize_pool": Decimal("1000.00"), "country": "TR", "start_date": date(2026, 1, 2)}
    assert matches_current("prize_pool", "1000", event) is True
    assert matches_current("country", "tr", event) is True
    assert matches_current("start_date", "2026-01-03", event) is False
    assert matches_current("city", None, event) is None

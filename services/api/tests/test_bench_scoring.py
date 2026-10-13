"""Scoring functions of the extraction benchmark (bench/scoring.py)."""

from datetime import date
from decimal import Decimal

import pytest
from extraction_bench import build_rating_sheet
from scoring import (
    normalize_text,
    normalize_url,
    percentile,
    score_field,
    score_page,
    summarize,
    values_match,
)


def test_normalize_text_folds_case_turkish_i_and_punctuation() -> None:
    assert normalize_text("  İstanbul,  TEKNİK  Üniversitesi! ") == "istanbul teknik üniversitesi"
    assert normalize_text("Chapel-Hill") == normalize_text("chapel hill")


def test_normalize_url_ignores_fragment_trailing_slash_and_host_case() -> None:
    assert normalize_url("HTTPS://Example.com/a/#top") == normalize_url("https://example.com/a")
    assert normalize_url("https://e.com/a?x=1") != normalize_url("https://e.com/a")


@pytest.mark.parametrize(
    ("field", "predicted", "gold", "expected"),
    [
        ("start_date", date(2026, 10, 9), "2026-10-09", True),
        ("start_date", date(2026, 10, 10), "2026-10-09", False),
        ("team_max", 4, 4, True),
        ("prize_pool", Decimal("200000.00"), 200000, True),
        ("prize_pool", Decimal("20000"), 200000, False),
        ("is_free", True, True, True),
        ("is_free", 1, True, False),
        ("currency", "try", "TRY", True),
        ("application_url", "https://a.com/x/", "https://a.com/x", True),
        ("organizer", "Borsa İstanbul & İTÜ", "Borsa İstanbul", True),  # containment
        ("title", "Hac", "Hackathon", False),  # too short to count as containment
        ("title", "Grid Up Hackathon", "grid up hackathon", True),
        ("city", "Ankara", "İstanbul", False),
    ],
)
def test_values_match(field: str, predicted: object, gold: object, expected: bool) -> None:
    assert values_match(field, predicted, gold) is expected


def test_score_field_outcomes() -> None:
    assert score_field("title", "X Hackathon", {"value": "X Hackathon"}) == "correct"
    assert score_field("title", "Y Hackathon", {"value": "X Hackathon"}) == "wrong"
    assert score_field("city", None, {"value": "Muğla"}) == "missed"
    assert score_field("city", "Muğla", {"value": None}) == "hallucinated"
    assert score_field("city", None, {"value": None}) == "ok_null"
    assert score_field("city", "Muğla", {"value": None, "ambiguous": True}) == "ignored"
    assert score_field("summary", "metin", {"value": None}) == "ignored"  # judged by hand
    assert score_field("eligibility", "x", {"value": "y"}) == "ignored"


def test_summarize_counts_accuracy_hallucinations_and_fabricated_dates() -> None:
    gold: dict[str, dict[str, object]] = {
        "title": {"value": "A"},
        "start_date": {"value": "2026-01-02"},
        "end_date": {"value": None},
        "venue": {"value": None},
    }
    good = score_page({"title": "A", "start_date": date(2026, 1, 2)}, gold)
    bad = score_page({"title": "B", "end_date": date(2026, 1, 3), "venue": "Hall"}, gold)
    summary = summarize([good, bad])
    assert good == {
        "title": "correct",
        "start_date": "correct",
        "end_date": "ok_null",
        "venue": "ok_null",
    }
    assert summary["accuracy"] == pytest.approx(2 / 4)  # correct, correct, wrong, missed
    assert summary["date_accuracy"] == pytest.approx(1 / 2)
    assert summary["hallucinations"] == 2
    assert summary["fabricated_dates"] == 1
    assert summary["hallucination_rate"] == pytest.approx(2 / 4)
    assert summary["per_field"]["title"] == pytest.approx(0.5)


def test_summarize_without_graded_fields_returns_none() -> None:
    assert summarize([])["accuracy"] is None


def test_percentile_nearest_rank() -> None:
    assert percentile([], 0.5) is None
    assert percentile([5.0], 0.95) == 5.0
    assert percentile([1.0, 2.0, 3.0, 4.0, 100.0], 0.5) == 3.0
    assert percentile([1.0, 2.0, 3.0, 4.0, 100.0], 1.0) == 100.0


def test_rating_sheet_hides_model_names_and_keeps_a_key() -> None:
    results = {
        "models": [
            {
                "model": "model-one",
                "runs": [{"page_id": "p1", "predictions": {"summary": "Özet bir"}}],
            },
            {"model": "model-two", "runs": [{"page_id": "p1", "predictions": {}}]},
        ]
    }
    sheet, key = build_rating_sheet(results)
    assert "model-one" not in sheet
    assert "model-two" not in sheet
    assert "Özet bir" in sheet
    assert "(no summary)" in sheet
    assert sorted(key["p1"].values()) == ["model-one", "model-two"]

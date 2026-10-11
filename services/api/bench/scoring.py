"""Pure scoring functions of the extraction benchmark (V1.2 part C).

Gold files (bench/data/gold/<id>.json) hold, per ExtractableField, `{"value", "snippet"}`
plus an optional `"ambiguous": true` (the page is contradictory or the field is judged by
hand): ambiguous fields are not scored at all. A gold `value` of null means "the page does
not state it", so any prediction there is a hallucination.

Outcome per field:
    correct       gold set, prediction equal under the field's comparison
    wrong         gold set, prediction set but different
    missed        gold set, no prediction
    hallucinated  gold null, prediction set
    ok_null       gold null, no prediction
    ignored       ambiguous gold, or a field that is judged by hand (summary, eligibility)
"""

import re
import unicodedata
from collections import Counter
from collections.abc import Mapping
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

Outcome = Literal["correct", "wrong", "missed", "hallucinated", "ok_null", "ignored"]

# Judged by hand (blind rating sheet), never by string comparison.
MANUAL_FIELDS = frozenset({"summary", "eligibility"})
DATE_FIELDS = frozenset({"start_date", "end_date", "application_deadline"})
URL_FIELDS = frozenset({"application_url"})
NUMBER_FIELDS = frozenset({"team_min", "team_max", "prize_pool"})
CODE_FIELDS = frozenset({"format", "country", "currency"})
BOOL_FIELDS = frozenset({"is_free"})
_MIN_CONTAINMENT = 4


def normalize_text(value: str) -> str:
    """Case-folded NFKC text with punctuation and runs of whitespace collapsed."""
    text = unicodedata.normalize("NFKC", value).replace("İ", "i").replace("ı", "i").casefold()
    text = re.sub(r"[^\w]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_url(value: str) -> str:
    parts = urlsplit(value.strip())
    path = parts.path.rstrip("/")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def _same_text(predicted: str, gold: str) -> bool:
    a, b = normalize_text(predicted), normalize_text(gold)
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = sorted((a, b), key=len)
    return len(shorter) >= _MIN_CONTAINMENT and shorter in longer


def _to_decimal(value: object) -> Decimal | None:
    if isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def values_match(field: str, predicted: object, gold: object) -> bool:
    """Compare one predicted value with one (non-null) gold value."""
    if field in DATE_FIELDS:
        predicted_text = predicted.isoformat() if isinstance(predicted, date) else str(predicted)
        return predicted_text == str(gold)
    if field in NUMBER_FIELDS:
        a, b = _to_decimal(predicted), _to_decimal(gold)
        return a is not None and a == b
    if field in BOOL_FIELDS:
        return isinstance(predicted, bool) and predicted == gold
    if field in URL_FIELDS:
        return normalize_url(str(predicted)) == normalize_url(str(gold))
    if field in CODE_FIELDS:
        return str(predicted).strip().casefold() == str(gold).strip().casefold()
    return _same_text(str(predicted), str(gold))


def score_field(field: str, predicted: object | None, gold_entry: Mapping[str, Any]) -> Outcome:
    if gold_entry.get("ambiguous") or field in MANUAL_FIELDS:
        return "ignored"
    gold = gold_entry.get("value")
    if gold is None:
        return "ok_null" if predicted is None else "hallucinated"
    if predicted is None:
        return "missed"
    return "correct" if values_match(field, predicted, gold) else "wrong"


def score_page(
    predictions: Mapping[str, object], gold_fields: Mapping[str, Mapping[str, Any]]
) -> dict[str, Outcome]:
    """Outcome for every field present in the gold file."""
    return {
        field: score_field(field, predictions.get(field), entry)
        for field, entry in gold_fields.items()
    }


def summarize(pages: list[dict[str, Outcome]]) -> dict[str, Any]:
    """Aggregate outcomes over pages.

    accuracy: correct / (correct + wrong + missed) over fields with a gold value.
    date_accuracy: the same, dates only.
    hallucinations: fields filled although gold is null; fabricated_dates: dates among them.
    """
    totals: Counter[Outcome] = Counter()
    date_totals: Counter[Outcome] = Counter()
    per_field: dict[str, Counter[Outcome]] = {}
    fabricated_dates = 0
    for outcomes in pages:
        for field, outcome in outcomes.items():
            totals[outcome] += 1
            per_field.setdefault(field, Counter())[outcome] += 1
            if field in DATE_FIELDS:
                date_totals[outcome] += 1
                if outcome == "hallucinated":
                    fabricated_dates += 1

    def rate(counter: Counter[Outcome]) -> float | None:
        graded = counter["correct"] + counter["wrong"] + counter["missed"]
        return counter["correct"] / graded if graded else None

    null_cases = totals["hallucinated"] + totals["ok_null"]
    return {
        "accuracy": rate(totals),
        "date_accuracy": rate(date_totals),
        "fabricated_dates": fabricated_dates,
        "hallucinations": totals["hallucinated"],
        "hallucination_rate": totals["hallucinated"] / null_cases if null_cases else None,
        "per_field": {field: rate(counter) for field, counter in sorted(per_field.items())},
    }


def percentile(values: list[float], fraction: float) -> float | None:
    """Nearest-rank percentile (fraction in 0..1) of a non-empty list."""
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]

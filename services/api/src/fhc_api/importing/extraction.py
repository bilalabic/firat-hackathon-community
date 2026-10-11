"""LLM extraction for URL import (AI_ARCHITECTURE §3, docs/planning/V1_2_URL_IMPORT.md part B).

    page ─► LLM (ExtractionOutput, untrusted envelope) ─► per-field validation (event rules)
         ─► evidence check (evidence.py) ─► merge with page.structured ─► cross-field rules

The model only proposes. Every value it returns is re-validated here; a field that fails is
dropped with a flag and the other fields are kept. LLM errors never raise: the structured
values are returned with `llm_error` set.
"""

import time
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, ValidationError

from fhc_api.common.clock import today_in
from fhc_api.events.models import DEFAULT_TIMEZONE, EventFormat, EventUpdate
from fhc_api.importing.evidence import (
    check_date,
    match_key,
    mentions_amount,
    mentions_count,
    occurs_in,
)
from fhc_api.importing.models import (
    EXTRACTABLE_FIELDS,
    ExtractableField,
    ExtractionResult,
    FieldFlag,
    FieldProposal,
    FieldValue,
    FlagKind,
    PageContent,
)
from fhc_api.importing.prompts import SYSTEM_PROMPT, build_user_message
from fhc_api.llm.provider import LLMError, LLMProvider

SNIPPET_MAX_CHARS = 300
_DETAIL_VALUE_CHARS = 50

# -- output schema ---------------------------------------------------------------------------
# Sent to Ollama as `format` (OllamaProvider passes `model_json_schema()`), so it stays plain:
# strings, integers, numbers, booleans, one enum, null. Caps follow the event field rules so
# the grammar keeps the model inside them; patterns, ranges and URL checks are applied per
# field afterwards, so one bad value does not fail the whole output.

Snippet = Annotated[str | None, Field(max_length=SNIPPET_MAX_CHARS)]


class _Text160(BaseModel):
    value: Annotated[str | None, Field(max_length=160)]
    snippet: Snippet


class _Text120(BaseModel):
    value: Annotated[str | None, Field(max_length=120)]
    snippet: Snippet


class _Text200(BaseModel):
    value: Annotated[str | None, Field(max_length=200)]
    snippet: Snippet


class _Text300(BaseModel):
    value: Annotated[str | None, Field(max_length=300)]
    snippet: Snippet


class _Text500(BaseModel):
    value: Annotated[str | None, Field(max_length=500)]
    snippet: Snippet


class _Code(BaseModel):
    value: Annotated[str | None, Field(max_length=3)]
    snippet: Snippet


class _Date(BaseModel):
    value: Annotated[str | None, Field(max_length=10, description="YYYY-MM-DD")]
    snippet: Snippet


class _Format(BaseModel):
    value: EventFormat | None
    snippet: Snippet


class _Integer(BaseModel):
    value: int | None
    snippet: Snippet


class _Number(BaseModel):
    value: float | None
    snippet: Snippet


class _Boolean(BaseModel):
    value: bool | None
    snippet: Snippet


class _Url(BaseModel):
    value: Annotated[str | None, Field(max_length=500)]
    snippet: Snippet


class ExtractionOutput(BaseModel):
    """What the model returns: one `{value, snippet}` object per ExtractableField."""

    title: _Text160
    organizer: _Text160
    summary: _Text300
    format: _Format
    city: _Text120
    country: _Code
    venue: _Text200
    start_date: _Date
    end_date: _Date
    application_deadline: _Date
    eligibility: _Text500
    team_min: _Integer
    team_max: _Integer
    prize_pool: _Number
    currency: _Code
    is_free: _Boolean
    application_url: _Url


# -- evidence rules per field ----------------------------------------------------------------

_DATE_FIELDS: tuple[ExtractableField, ...] = ("start_date", "end_date", "application_deadline")
# Values copied from the page: the value itself must occur in its snippet.
_QUOTED_FIELDS = frozenset(
    {"title", "organizer", "city", "venue", "eligibility", "application_url"}
)
# Values the model derives (a code, an enum, a Turkish sentence): only the snippet is checked.
_DERIVED_FIELDS = frozenset({"summary", "format", "country", "currency", "is_free"})

# A year outside fetch year -1 … +2 is a misread (an old edition, a typo), not a plan.
YEARS_BEFORE = 1
YEARS_AFTER = 2


def _short(value: object) -> str:
    text = value.isoformat() if isinstance(value, date) else str(value)
    return text if len(text) <= _DETAIL_VALUE_CHARS else f"{text[: _DETAIL_VALUE_CHARS - 1]}…"


def _validation_message(exc: ValidationError) -> str:
    # include_input=False: the model's value is not echoed into the operator-facing detail.
    errors = exc.errors(include_url=False, include_input=False)
    return errors[0]["msg"] if errors else "invalid value"


def _same(field: ExtractableField, a: FieldValue, b: FieldValue) -> bool:
    if isinstance(a, str) and isinstance(b, str) and field != "application_url":
        return match_key(a) == match_key(b)
    return a == b


class LLMExtractor:
    """`Extractor` backed by an LLMProvider. `model_label` names the model in `extracted_by`
    ("llm:<model_label>"); `now` is the monotonic clock for `llm_duration_ms` (tests)."""

    def __init__(
        self,
        provider: LLMProvider,
        *,
        model_label: str,
        now: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._provider = provider
        self._model_label = model_label
        self._now = now

    def extract(self, page: PageContent) -> ExtractionResult:
        fetch_date = _fetch_date(page)
        flags: list[FieldFlag] = []
        llm_fields: dict[ExtractableField, FieldProposal] = {}
        llm_error: str | None = None
        extracted_by: str | None = None

        started = self._now()
        try:
            output = self._provider.generate_structured(
                system=SYSTEM_PROMPT,
                user=build_user_message(page, fetch_date),
                schema=ExtractionOutput,
            )
        except LLMError as exc:
            llm_error = f"LLM extraction failed: {exc}"
        else:
            extracted_by = f"llm:{self._model_label}"
            llm_fields = _check_output(output, page, fetch_date, flags)
        duration_ms = round((self._now() - started) * 1000)

        fields = _merge(page, llm_fields, flags)
        _apply_rules(fields, fetch_date, flags)
        return ExtractionResult(
            page=page,
            fields=fields,
            flags=flags,
            extracted_by=extracted_by,
            llm_error=llm_error,
            llm_duration_ms=duration_ms,
        )


def _fetch_date(page: PageContent) -> date:
    if page.fetched_at.tzinfo is None:
        return page.fetched_at.date()
    return today_in(DEFAULT_TIMEZONE, page.fetched_at)


# -- per-field validation and evidence -------------------------------------------------------


def _check_output(
    output: ExtractionOutput, page: PageContent, fetch_date: date, flags: list[FieldFlag]
) -> dict[ExtractableField, FieldProposal]:
    # The model sees the title line and the text; a quote from either counts as page content.
    page_key = match_key(f"{page.title or ''}\n{page.text}")
    proposals: dict[ExtractableField, FieldProposal] = {}

    def flag(field: ExtractableField, kind: FlagKind, detail: str) -> None:
        flags.append(FieldFlag(field=field, kind=kind, detail=detail))

    for name in EXTRACTABLE_FIELDS:
        item = getattr(output, name)
        if item.value is None:
            continue
        try:
            value = _validated(name, item.value)
        except _InvalidValue as exc:
            flag(name, "invalid", f"Dropped the LLM value: {exc}.")
            continue
        if value is None:  # blank text: nothing proposed
            continue
        snippet = (item.snippet or "").strip()
        if not snippet:
            flag(name, "unsupported", "Dropped the LLM value: no supporting snippet.")
            continue
        if not occurs_in(snippet, page_key):
            flag(name, "unsupported", "Dropped the LLM value: the snippet is not in the page text.")
            continue
        try:
            supported = _supported(name, value, snippet, fetch_date)
        except _Unsupported as exc:
            flag(name, "unsupported", f"Dropped the LLM value: {exc}.")
            continue
        proposals[name] = FieldProposal(field=name, value=supported, source="llm", snippet=snippet)
    return proposals


class _InvalidValue(ValueError):
    """The model's value fails the event field rules. The message never contains the value."""


class _Unsupported(ValueError):
    """The snippet does not state the model's value."""


def _validated(name: ExtractableField, raw: object) -> FieldValue | None:
    """`raw` checked against the event field rules (EventUpdate); None for a blank text.
    Raises _InvalidValue."""
    if name in _DATE_FIELDS:
        try:
            raw = date.fromisoformat(str(raw))
        except ValueError:
            raise _InvalidValue("the date is not YYYY-MM-DD") from None
    elif name == "prize_pool" and isinstance(raw, float):
        # 50000.0 → Decimal(50000), 1.5 → Decimal("1.5"); never the binary float expansion.
        raw = Decimal(int(raw)) if raw.is_integer() else Decimal(str(raw))
    try:
        update = EventUpdate.model_validate({name: raw})
    except ValidationError as exc:
        raise _InvalidValue(_validation_message(exc)) from None
    value: FieldValue | None = getattr(update, name)
    return value


def _supported(
    name: ExtractableField, value: FieldValue, snippet: str, fetch_date: date
) -> FieldValue:
    """The value (a date possibly with the inferred year) when the snippet supports it.
    Raises _Unsupported with the reason."""
    if name in _DERIVED_FIELDS:
        return value
    if name in _QUOTED_FIELDS:
        if not (isinstance(value, str) and occurs_in(value, match_key(snippet))):
            raise _Unsupported("the value is not in its snippet")
        return value
    if isinstance(value, date):
        evidence = check_date(value, snippet, fetch_date)
        if evidence.value is None:
            raise _Unsupported(evidence.reason)
        return evidence.value
    if isinstance(value, Decimal):
        if not mentions_amount(value, snippet):
            raise _Unsupported("the amount is not in its snippet")
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if not mentions_count(value, snippet):
            raise _Unsupported("the number is not in its snippet")
        return value
    return value


# -- merge and cross-field rules -------------------------------------------------------------


def _merge(
    page: PageContent,
    llm_fields: dict[ExtractableField, FieldProposal],
    flags: list[FieldFlag],
) -> dict[ExtractableField, FieldProposal]:
    """Structured data wins; a supported LLM value that differs becomes a `conflict` flag."""
    fields: dict[ExtractableField, FieldProposal] = {}
    for name in EXTRACTABLE_FIELDS:
        structured = page.structured.get(name)
        proposal = llm_fields.get(name)
        if structured is None:
            if proposal is not None:
                fields[name] = proposal
            continue
        fields[name] = FieldProposal(
            field=name,
            value=structured.value,
            source=structured.source,
            snippet=structured.snippet[:SNIPPET_MAX_CHARS],
        )
        if proposal is not None and not _same(name, structured.value, proposal.value):
            flags.append(
                FieldFlag(
                    field=name,
                    kind="conflict",
                    detail=f"Kept {structured.source} value {_short(structured.value)!r}; "
                    f"the LLM proposed {_short(proposal.value)!r}.",
                )
            )
    return fields


def _apply_rules(
    fields: dict[ExtractableField, FieldProposal], fetch_date: date, flags: list[FieldFlag]
) -> None:
    def drop(name: ExtractableField, detail: str) -> None:
        del fields[name]
        flags.append(FieldFlag(field=name, kind="rule_violation", detail=detail))

    def pair_drop(first: ExtractableField, second: ExtractableField, detail: str) -> None:
        # Drop the LLM side of a contradiction; when both values are structured, drop both.
        llm = [name for name in (first, second) if fields[name].source == "llm"]
        for name in llm or [first, second]:
            drop(name, detail)

    for name in _DATE_FIELDS:
        proposal = fields.get(name)
        if proposal is None or not isinstance(proposal.value, date):
            continue
        low, high = fetch_date.year - YEARS_BEFORE, fetch_date.year + YEARS_AFTER
        if not low <= proposal.value.year <= high:
            drop(name, f"Dropped: the year {proposal.value.year} is outside {low}-{high}.")

    def value(name: ExtractableField) -> FieldValue | None:
        proposal = fields.get(name)
        return proposal.value if proposal is not None else None

    start, end = value("start_date"), value("end_date")
    if isinstance(start, date) and isinstance(end, date) and start > end:
        pair_drop(
            "start_date",
            "end_date",
            f"Dropped: start date {start.isoformat()} is after end date {end.isoformat()}.",
        )

    deadline, end = value("application_deadline"), value("end_date")
    if isinstance(deadline, date) and isinstance(end, date) and deadline > end:
        drop(
            "application_deadline",
            f"Dropped: deadline {deadline.isoformat()} is after end date {end.isoformat()}.",
        )

    team_min, team_max = value("team_min"), value("team_max")
    if isinstance(team_min, int) and isinstance(team_max, int) and team_min > team_max:
        pair_drop(
            "team_min",
            "team_max",
            f"Dropped: minimum team size {team_min} is above the maximum {team_max}.",
        )

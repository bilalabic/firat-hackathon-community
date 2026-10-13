"""LLM extraction for URL import (AI_ARCHITECTURE §3, docs/planning/V1_2_URL_IMPORT.md part B).

    page ─► LLM (ExtractionOutput, untrusted envelope) ─► per-field validation (event rules)
         ─► evidence check (evidence.py) ─► merge with page.structured ─► cross-field rules

The model only proposes. Every value it returns is re-validated here; a field that fails is
dropped with a flag and the other fields are kept. When the model's quote is missing or does
not hold up, code looks for a page line that supports the value under the same rules; a
value is never kept without a located page span. LLM errors never raise: the structured
values are returned with `llm_error` set.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, ValidationError

from fhc_api.common.clock import today_in
from fhc_api.common.normalize import normalize_url
from fhc_api.events.models import DEFAULT_TIMEZONE, EventFormat, EventUpdate
from fhc_api.importing.evidence import (
    check_date,
    evidence_spans,
    long_enough,
    looks_like_instruction,
    match_key,
    mentions_amount,
    mentions_team_size,
    occurs_as_phrase,
    occurs_in,
    page_evidence_key,
    supports_country,
    supports_currency,
    supports_format,
    supports_is_free,
    url_in_text,
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
# Sent to Ollama as `format` (OllamaProvider passes `model_json_schema()`) and to OpenAI as a
# strict json_schema (`llm.openai.to_strict_schema`), so it stays plain:
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
# Values copied from the page: the value itself must occur in its snippet as whole words.
_QUOTED_FIELDS = frozenset({"title", "organizer", "city", "venue", "eligibility"})

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
        checked = _Checked({}, set())
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
            checked = _check_output(output, page, fetch_date, flags)
        duration_ms = round((self._now() - started) * 1000)

        fields = _merge(page, checked.proposals, flags)
        _apply_rules(fields, fetch_date, flags, checked.year_inferred)
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


@dataclass(frozen=True)
class _Checked:
    proposals: dict[ExtractableField, FieldProposal]
    # Dates whose year came from the fetch date, not from the page (see _apply_rules).
    year_inferred: set[ExtractableField]


def _check_output(
    output: ExtractionOutput, page: PageContent, fetch_date: date, flags: list[FieldFlag]
) -> _Checked:
    # The model sees the title line and the text; a quote from either counts as page content.
    page_text = f"{page.title or ''}\n{page.text}"
    page_key = page_evidence_key(page_text)
    spans: list[str] | None = None  # built on first use
    checked = _Checked({}, set())

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

        if name == "application_url" and _is_page_url(value, page):
            flag(name, "invalid", "Dropped the LLM value: the URL is the imported page itself.")
            continue

        snippet = (item.snippet or "").strip()
        reason = _unusable(snippet, page_key)
        supported: tuple[FieldValue, bool] | None = None
        if reason is None:
            try:
                supported = _supported(name, value, snippet, fetch_date)
            except _Unsupported as exc:
                reason = str(exc)
        # The model's quote is missing or does not hold up: look for a page line that
        # supports the value under the same rules. The summary is the model's own sentence,
        # so it has no page line to find. A date whose quote has no year ("13-14 Mayıs")
        # also looks for a line that states the model's full date ("13-14 Mayıs 2026"):
        # a year from the page beats one inferred from the fetch date.
        year_missing = supported is not None and supported[1]
        if (supported is None or year_missing) and name != "summary":
            if spans is None:
                spans = evidence_spans(page_text)
            located = _locate(name, value, spans, fetch_date)
            if located is not None and (supported is None or located[1] == (value, False)):
                snippet, supported = located
            elif supported is None:
                reason = f"{reason}, and no page line supports the value"
        if supported is None:
            flag(name, "unsupported", f"Dropped the LLM value: {reason}.")
            continue
        final, inferred = supported
        checked.proposals[name] = FieldProposal(
            field=name, value=final, source="llm", snippet=snippet[:SNIPPET_MAX_CHARS]
        )
        if inferred:
            checked.year_inferred.add(name)
    return checked


def _is_page_url(value: FieldValue, page: PageContent) -> bool:
    """The imported page is the event page, not its application form."""
    pages = {normalize_url(page.requested_url), normalize_url(page.final_url)}
    return isinstance(value, str) and normalize_url(value) in pages


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


def _unusable(snippet: str, page_key: str) -> str | None:
    """Why the model's snippet cannot be evidence, or None."""
    if not snippet:
        return "no supporting snippet"
    if not long_enough(snippet):
        return "the snippet is too short to be evidence"
    if looks_like_instruction(snippet):
        return "the snippet reads like an instruction to the model"
    if not occurs_in(snippet, page_key):
        return "the snippet is not in the page text"
    return None


def _supported(
    name: ExtractableField, value: FieldValue, snippet: str, fetch_date: date
) -> tuple[FieldValue, bool]:
    """(value, year_inferred) when the snippet states the value; a date may get the year
    from the fetch date. Raises _Unsupported with the reason."""
    if isinstance(value, date):
        evidence = check_date(value, snippet, fetch_date)
        if evidence.value is None:
            raise _Unsupported(evidence.reason)
        return evidence.value, evidence.year_inferred
    ok: bool
    if name == "summary":
        ok = True
    elif name in _QUOTED_FIELDS:
        ok = isinstance(value, str) and occurs_as_phrase(value, snippet)
    elif name == "application_url":
        ok = isinstance(value, str) and url_in_text(value, snippet)
    elif name == "format":
        ok = isinstance(value, str) and supports_format(value, snippet)
    elif name == "country":
        ok = isinstance(value, str) and supports_country(value, snippet)
    elif name == "currency":
        ok = isinstance(value, str) and supports_currency(value, snippet)
    elif name == "is_free":
        ok = isinstance(value, bool) and supports_is_free(value, snippet)
    elif name == "prize_pool":
        ok = isinstance(value, Decimal) and mentions_amount(value, snippet)
    else:  # team_min, team_max
        ok = isinstance(value, int) and mentions_team_size(value, snippet)
    if not ok:
        raise _Unsupported(_UNSUPPORTED_REASONS.get(name, "the value is not in its snippet"))
    return value, False


_UNSUPPORTED_REASONS: dict[str, str] = {
    "application_url": "the URL is not in its snippet",
    "format": "the snippet does not name this format",
    "country": "the snippet does not name this country",
    "currency": "the snippet does not name this currency",
    "is_free": "the snippet does not say whether taking part is free",
    "prize_pool": "the snippet does not give this prize amount",
    "team_min": "the snippet does not give this team size",
    "team_max": "the snippet does not give this team size",
}


def _locate(
    name: ExtractableField, value: FieldValue, spans: list[str], fetch_date: date
) -> tuple[str, tuple[FieldValue, bool]] | None:
    """The first page span that supports `value`. For a date, a span that states the model's
    exact date (with its year) wins over an earlier one that needs the year inferred."""
    fallback: tuple[str, tuple[FieldValue, bool]] | None = None
    for span in spans:
        try:
            supported = _supported(name, value, span, fetch_date)
        except _Unsupported:
            continue
        if supported == (value, False):
            return span, supported
        fallback = fallback or (span, supported)
    return fallback


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
    fields: dict[ExtractableField, FieldProposal],
    fetch_date: date,
    flags: list[FieldFlag],
    year_inferred: set[ExtractableField],
) -> None:
    def value(name: ExtractableField) -> FieldValue | None:
        proposal = fields.get(name)
        return proposal.value if proposal is not None else None

    def drop(name: ExtractableField, detail: str) -> None:
        del fields[name]
        flags.append(FieldFlag(field=name, kind="rule_violation", detail=detail))

    def is_llm(name: ExtractableField) -> bool:
        return fields[name].source == "llm"

    def drop_pair(first: ExtractableField, second: ExtractableField, detail: str) -> None:
        # Drop the LLM side of a contradiction; when both have the same kind of source, both.
        llm = [name for name in (first, second) if is_llm(name)]
        for name in llm if len(llm) == 1 else [first, second]:
            drop(name, detail)

    # A range across New Year without years ("28 Aralık - 3 Ocak") resolves each date on its
    # own; when the earlier date's year was inferred and it lands after the later one, the
    # previous year is the reading that fits ("28 Aralık" fetched in January).
    ordered: tuple[tuple[ExtractableField, ExtractableField], ...] = (
        ("start_date", "end_date"),
        ("application_deadline", "end_date"),
    )
    for earlier, later in ordered:
        first, last = value(earlier), value(later)
        if (
            earlier in year_inferred
            and isinstance(first, date)
            and isinstance(last, date)
            and first > last
        ):
            try:
                shifted = first.replace(year=first.year - 1)
            except ValueError:  # 29 February
                continue
            if shifted <= last:
                fields[earlier] = replace(fields[earlier], value=shifted)

    for name in _DATE_FIELDS:
        day = value(name)
        if not isinstance(day, date):
            continue
        low, high = fetch_date.year - YEARS_BEFORE, fetch_date.year + YEARS_AFTER
        if not low <= day.year <= high:
            drop(name, f"Dropped: the year {day.year} is outside {low}-{high}.")

    start, end = value("start_date"), value("end_date")
    if isinstance(start, date) and isinstance(end, date) and start > end:
        detail = f"Dropped: start date {start.isoformat()} is after end date {end.isoformat()}."
        drop_pair("start_date", "end_date", detail)

    deadline, end = value("application_deadline"), value("end_date")
    if isinstance(deadline, date) and isinstance(end, date) and deadline > end:
        detail = f"Dropped: deadline {deadline.isoformat()} is after end date {end.isoformat()}."
        # Structured data wins; with the same kind of source on both sides, the deadline goes.
        if is_llm("end_date") and not is_llm("application_deadline"):
            drop("end_date", detail)
        else:
            drop("application_deadline", detail)

    # `currency` is the prize pool's currency: without a pool it describes nothing (a grant,
    # a fee or one first prize mentioned in passing). A structured currency stays.
    if "currency" in fields and "prize_pool" not in fields and is_llm("currency"):
        drop("currency", "Dropped: a currency without a prize pool.")

    # An online event has no place: an LLM city, venue or country is about something else
    # ("Türkiye'nin en büyük ...", "US only" eligibility). Structured values stay.
    if value("format") == "online":
        for name in ("city", "venue", "country"):
            if name in fields and is_llm(name):
                drop(name, "Dropped: the event is online, so it has no place.")

    team_min, team_max = value("team_min"), value("team_max")
    if isinstance(team_min, int) and isinstance(team_max, int) and team_min > team_max:
        detail = f"Dropped: minimum team size {team_min} is above the maximum {team_max}."
        drop_pair("team_min", "team_max", detail)

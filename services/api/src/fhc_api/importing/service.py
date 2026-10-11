"""URL import (V1.2, docs/planning/V1_2_URL_IMPORT.md): a pasted URL becomes a draft event
with field-level evidence. AI proposes, code decides, a human approves: the event is
always a `draft`, `unverified`; review and publishing stay manual.

Flow of `UrlImporter.import_url` (synchronous; the admin waits):

1. Static URL check (http(s), public host) and the exact duplicate check on
   `events.official_url_normalized`: an existing event is returned, nothing is fetched.
2. A run row (`app.runs`, `running`) is committed, so an interrupted import stays visible.
3. `PageLoader.load_page` (network, up to ~60 s over redirects) and `Extractor.extract`
   (local LLM, up to OLLAMA_TIMEOUT_S, ~60 s on a cold start). No database connection is
   held meanwhile. Expected total: 5-90 s; the admin client waits up to 240 s.
4. One transaction: duplicate re-check (redirect target, concurrent imports), the draft
   event, its `official` event source, the evidence rows, the run (`succeeded`, stats)
   and the audit entry.

A `PageError` ends the run as `failed` with the loader's operator-facing message (422).
An LLM failure is not an error: the extractor returns the structured values only and
`llm_error`, and the draft is created from those.

`official_url` is the requested URL, or the final URL after redirects when the redirect
stayed on the same site (same host, ignoring `www.`): such redirects are canonical forms
(https, trailing slash, language path). A cross-site redirect (link shortener, platform
login) keeps the requested URL; the final URL is kept in the run stats.
"""

import logging
import re
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import HTTPException
from psycopg.rows import DictRow
from pydantic import ValidationError

from fhc_api.common import audit
from fhc_api.common.errors import conflict, not_found, unprocessable
from fhc_api.common.fields import check_http_url
from fhc_api.common.normalize import normalize_url
from fhc_api.db import Conn, ConnFactory
from fhc_api.events import repository as events_repository
from fhc_api.events import service as events_service
from fhc_api.events.models import EventCreate, EventUpdate
from fhc_api.importing import repository
from fhc_api.importing.api_models import (
    EvidenceOut,
    FieldEvidenceOut,
    FlagOut,
    RunOut,
    RunPage,
    UrlImportOut,
)
from fhc_api.importing.models import (
    EXTRACTABLE_FIELDS,
    ExtractableField,
    ExtractionResult,
    Extractor,
    FieldFlag,
    FieldProposal,
    FieldValue,
    PageContent,
    PageError,
    PageLoader,
)
from fhc_api.sources import repository as sources_repository

logger = logging.getLogger(__name__)

RUN_KIND = "url_import"
NOT_AVAILABLE = "URL import is not available: the page loader or the extractor is not configured"
INTERNAL_ERROR = "internal error during the import (see the API log)"
TITLE_MIN, TITLE_MAX = 3, 160
SNIPPET_MAX = 500
DETAIL_MAX = 500
STATS_TEXT_MAX = 500

# consistency_problems() message -> the field dropped to resolve it.
_CONSISTENCY_DROPS: dict[str, ExtractableField] = {
    "end_date is before start_date": "end_date",
    "team_min is greater than team_max": "team_max",
    "currency is required when prize_pool is set": "prize_pool",
}


# --- pure helpers ---------------------------------------------------------------------


def value_text(value: object) -> str:
    """Text form of a field value, as stored in `event_field_evidence.value_text`."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    return str(value)


def _comparable(field: str, value: object) -> str | None:
    if value is None:
        return None
    text = value_text(value).strip()
    return text.upper() if field in ("country", "currency") else text


def matches_current(field: str, proposed: str | None, event: Mapping[str, Any]) -> bool | None:
    """Whether the event still holds the proposed value (null without a value)."""
    if proposed is None:
        return None
    current = event.get(field)
    if isinstance(current, Decimal):
        try:
            return Decimal(proposed) == current
        except ArithmeticError:
            return False
    return _comparable(field, current) == _comparable(field, proposed)


def _host(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def same_site(a: str, b: str) -> bool:
    return bool(_host(a)) and _host(a) == _host(b)


def choose_official_url(requested: str, final: str) -> str:
    """The final URL after a same-site redirect, else the requested URL (module doc)."""
    if final == requested or not same_site(requested, final):
        return requested
    try:
        check_http_url(final)
    except ValueError:
        return requested
    if events_service.official_url_problem(final) is not None:
        return requested
    return final


def clean_title(text: str | None) -> str | None:
    if not text:
        return None
    title = re.sub(r"\s+", " ", text).strip()
    if len(title) > TITLE_MAX:
        title = title[: TITLE_MAX - 1].rstrip() + "…"
    return title if len(title) >= TITLE_MIN else None


def _clip(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass(frozen=True)
class Draft:
    """The event values and the evidence derived from one extraction."""

    values: dict[str, Any]  # EventCreate input (without official_url)
    proposals: list[FieldProposal]  # kept values, title included
    flags: list[FieldFlag]


def build_draft(result: ExtractionResult, *, fallback_host: str) -> Draft:
    """Validate each proposed value again with the event field rules (defense in depth:
    the extractor already did), drop what fails, and resolve cross-field rules by dropping
    the later field. Every dropped value becomes an `invalid`/`rule_violation` flag."""
    flags = list(result.flags)
    kept: dict[ExtractableField, FieldProposal] = {}
    values: dict[str, Any] = {}
    for field in EXTRACTABLE_FIELDS:
        proposal = result.fields.get(field)
        if proposal is None:
            continue
        try:
            model = EventUpdate.model_validate({field: proposal.value})
        except ValidationError:
            flags.append(
                FieldFlag(field, "invalid", "The value does not pass the event field rules.")
            )
            continue
        value = getattr(model, field)
        if value is None:
            continue
        kept[field] = proposal
        values[field] = value

    while problems := events_service.consistency_problems(values):
        problem = next((p for p in problems if p in _CONSISTENCY_DROPS), None)
        if problem is None:  # pragma: no cover - every consistency rule is mapped
            raise RuntimeError(f"unmapped consistency problem: {problems}")
        dropped = _CONSISTENCY_DROPS[problem]
        flags.append(FieldFlag(dropped, "rule_violation", f"Dropped: {problem}."))
        values.pop(dropped)
        kept.pop(dropped)

    if "title" not in values:
        page_title = clean_title(result.page.title)
        if page_title is not None:
            values["title"] = page_title
            kept["title"] = FieldProposal(
                "title", page_title, "meta", _clip(result.page.title, 300)
            )
        else:
            values["title"] = clean_title(f"Imported from {fallback_host}") or "Imported event"
    return Draft(values=values, proposals=list(kept.values()), flags=flags)


def _stats(
    *,
    page: PageContent | None = None,
    result: ExtractionResult | None = None,
    draft: Draft | None = None,
    timings: Mapping[str, int],
    outcome: str | None = None,
    official_url: str | None = None,
) -> dict[str, Any]:
    stats: dict[str, Any] = {f"{name}_ms": ms for name, ms in timings.items()}
    if outcome:
        stats["outcome"] = outcome
    if page is not None:
        stats["final_url"] = _clip(page.final_url, STATS_TEXT_MAX)
        stats["text_chars"] = len(page.text)
        stats["text_truncated"] = page.text_truncated
        stats["structured_fields"] = len(page.structured)
        if page.image_url:
            stats["image_url"] = _clip(page.image_url, STATS_TEXT_MAX)
    if official_url is not None:
        stats["official_url"] = official_url
    if result is not None:
        stats["extracted_by"] = result.extracted_by
        stats["llm_error"] = _clip(result.llm_error, STATS_TEXT_MAX)
        stats["llm_ms"] = result.llm_duration_ms
    if draft is not None:
        stats["fields"] = len(draft.proposals)
        stats["fields_by_source"] = dict(Counter(p.source for p in draft.proposals))
        stats["flags"] = len(draft.flags)
        stats["flags_by_kind"] = dict(Counter(f.kind for f in draft.flags))
    return stats


def _ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def run_out(row: Mapping[str, Any]) -> RunOut:
    input_ = row.get("input") or {}
    return RunOut.model_validate(
        {**row, "url": input_.get("url") if isinstance(input_, dict) else None}
    )


# --- service --------------------------------------------------------------------------


class UrlImporter:
    """Built once per app. `page_loader` and `extractor` are injected (V1.2 parts A and B);
    without either, the import endpoint answers 409 `URL import is not available`."""

    def __init__(self, page_loader: PageLoader | None, extractor: Extractor | None) -> None:
        self._loader = page_loader
        self._extractor = extractor

    def import_url(self, open_conn: ConnFactory, url: str, *, actor: str) -> UrlImportOut:
        if self._loader is None or self._extractor is None:
            raise conflict(NOT_AVAILABLE)
        if problem := events_service.official_url_problem(url):
            raise unprocessable(problem.replace("official_url", "url"))
        requested_normalized = normalize_url(url)

        with open_conn() as conn:
            existing = repository.find_event_by_url(conn, [requested_normalized])
            if existing is not None:
                return UrlImportOut(outcome="duplicate", event_id=existing["id"], run=None)
            run = repository.insert_run(conn, kind=RUN_KIND, input_={"url": url})

        run_id: UUID = run["id"]
        timings: dict[str, int] = {}
        started = time.perf_counter()
        try:
            page = self._loader.load_page(url)
        except PageError as exc:
            timings["page"] = timings["total"] = _ms(started)
            message = str(exc) or "the page could not be read"
            self._fail(open_conn, run_id, message, _stats(timings=timings))
            raise unprocessable(message) from None
        except Exception:
            self._fail_internal(open_conn, run_id, _stats(timings={"total": _ms(started)}))
            raise
        timings["page"] = _ms(started)

        try:
            step = time.perf_counter()
            result = self._extractor.extract(page)
            timings["extract"] = _ms(step)
            return self._save(open_conn, run_id, url, page, result, timings, started, actor)
        except HTTPException as exc:
            timings["total"] = _ms(started)
            self._fail(open_conn, run_id, str(exc.detail), _stats(page=page, timings=timings))
            raise
        except Exception:
            timings["total"] = _ms(started)
            self._fail_internal(open_conn, run_id, _stats(page=page, timings=timings))
            raise

    def _fail_internal(self, open_conn: ConnFactory, run_id: UUID, stats: dict[str, Any]) -> None:
        logger.exception("URL import run %s failed", run_id)
        self._fail(open_conn, run_id, INTERNAL_ERROR, stats)

    @staticmethod
    def _fail(open_conn: ConnFactory, run_id: UUID, error: str, stats: dict[str, Any]) -> None:
        try:
            with open_conn() as conn:
                repository.finish_run(
                    conn, run_id, status="failed", stats=stats, error=error[:2000]
                )
        except Exception:  # the original error matters more; the run stays `running`
            logger.exception("could not record the failure of run %s", run_id)

    def _save(
        self,
        open_conn: ConnFactory,
        run_id: UUID,
        url: str,
        page: PageContent,
        result: ExtractionResult,
        timings: dict[str, int],
        started: float,
        actor: str,
    ) -> UrlImportOut:
        official_url = choose_official_url(url, page.final_url)
        draft = build_draft(result, fallback_host=_host(official_url) or "the page")
        candidates = sorted(
            {normalize_url(url), normalize_url(official_url), normalize_url(page.final_url)}
        )
        with open_conn() as conn, conn.transaction():
            # Serializes concurrent imports of the same URL; released at commit.
            conn.execute(
                "select pg_advisory_xact_lock(hashtext('url_import:' || %s))",
                (normalize_url(official_url),),
            )
            existing = repository.find_event_by_url(conn, candidates)
            if existing is not None:
                timings["total"] = _ms(started)
                row = repository.finish_run(
                    conn,
                    run_id,
                    status="succeeded",
                    event_id=existing["id"],
                    stats=_stats(page=page, result=result, timings=timings, outcome="duplicate"),
                )
                return UrlImportOut(outcome="duplicate", event_id=existing["id"], run=run_out(row))

            event = events_service.create_event(
                conn,
                EventCreate.model_validate({**draft.values, "official_url": official_url}),
                discovered_at=page.fetched_at,
            )
            event_source_id = sources_repository.insert_event_source(
                conn,
                {
                    "event_id": event["id"],
                    "source_id": repository.manual_source_id(conn),
                    "url": official_url,
                    "url_normalized": event["official_url_normalized"],
                    "role": "official",
                },
            )
            repository.insert_evidence(
                conn, _evidence_rows(event["id"], run_id, event_source_id, draft, result)
            )
            timings["total"] = _ms(started)
            stats = _stats(
                page=page,
                result=result,
                draft=draft,
                timings=timings,
                outcome="created",
                official_url=official_url,
            )
            row = repository.finish_run(
                conn, run_id, status="succeeded", event_id=event["id"], stats=stats
            )
            audit.record(
                conn,
                actor=actor,
                action="url_import",
                entity_type="event",
                entity_id=event["id"],
                detail={
                    "run_id": str(run_id),
                    "fields": len(draft.proposals),
                    "flags": len(draft.flags),
                    "llm": result.extracted_by is not None,
                },
            )
        return UrlImportOut(outcome="created", event_id=event["id"], run=run_out(row))

    # --- reads ------------------------------------------------------------------------

    @staticmethod
    def list_runs(conn: Conn, *, limit: int, offset: int) -> RunPage:
        rows, total = repository.list_runs(conn, limit=limit, offset=offset)
        return RunPage(
            items=[run_out(row) for row in rows], total=total, limit=limit, offset=offset
        )

    @staticmethod
    def evidence(conn: Conn, event_id: UUID) -> EvidenceOut:
        event = events_repository.get(conn, event_id)
        if event is None:
            raise not_found("event")
        rows = repository.latest_evidence(conn, event_id)
        run = repository.get_run(conn, rows[0]["run_id"]) if rows and rows[0]["run_id"] else None
        return EvidenceOut(
            event_id=event_id,
            run=run_out(run) if run else None,
            extracted_at=rows[0]["extracted_at"] if rows else None,
            fields=group_evidence(rows, event),
        )


def _evidence_rows(
    event_id: UUID,
    run_id: UUID,
    event_source_id: UUID,
    draft: Draft,
    result: ExtractionResult,
) -> list[dict[str, Any]]:
    base = {"event_id": event_id, "run_id": run_id, "event_source_id": event_source_id}
    rows: list[dict[str, Any]] = [
        {
            **base,
            "field": proposal.field,
            "value_text": value_text(_validated(draft, proposal)),
            "source": proposal.source,
            "extracted_by": (result.extracted_by or "llm")
            if proposal.source == "llm"
            else proposal.source,
            "snippet": _clip(proposal.snippet, SNIPPET_MAX),
        }
        for proposal in draft.proposals
    ]
    rows += [
        {
            **base,
            "field": flag.field,
            "flag": flag.kind,
            "flag_detail": _clip(flag.detail, DETAIL_MAX) or flag.kind,
        }
        for flag in draft.flags
    ]
    return rows


def _validated(draft: Draft, proposal: FieldProposal) -> FieldValue:
    """The value as stored on the event (after the field rules, e.g. upper-cased codes)."""
    value: FieldValue = draft.values.get(proposal.field, proposal.value)
    return value


def group_evidence(rows: Sequence[DictRow], event: Mapping[str, Any]) -> list[FieldEvidenceOut]:
    """One entry per field: the proposed value (if any) and its flags, in form order."""
    by_field: dict[str, dict[str, Any]] = {}
    for row in rows:
        entry = by_field.setdefault(
            row["field"],
            {
                "field": row["field"],
                "value_text": None,
                "source": None,
                "extracted_by": None,
                "snippet": None,
                "flags": [],
            },
        )
        if row["value_text"] is not None:
            entry.update(
                value_text=row["value_text"],
                source=row["source"],
                extracted_by=row["extracted_by"],
                snippet=row["snippet"],
            )
        if row["flag"] is not None:
            entry["flags"].append(FlagOut(kind=row["flag"], detail=row["flag_detail"]))
    order = {field: index for index, field in enumerate(EXTRACTABLE_FIELDS)}
    return [
        FieldEvidenceOut(
            **entry, matches_current=matches_current(entry["field"], entry["value_text"], event)
        )
        for entry in sorted(
            by_field.values(), key=lambda e: (order.get(e["field"], len(order)), e["field"])
        )
    ]

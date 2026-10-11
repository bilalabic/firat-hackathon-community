"""Shared types of the URL import pipeline (V1.2, docs/planning/V1_2_URL_IMPORT.md).

    url ─► PageLoader.load_page ─► PageContent ─► Extractor.extract ─► ExtractionResult
                (page.py)                            (extraction.py)          │
                                                                   service.py ▼
                                                draft event + app.event_field_evidence

These types are the contract between the three parts; change them only together.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Protocol, get_args

# Event fields the pipeline may propose. `official_url` is the imported URL itself, and
# `description`, `categories`, `technologies` and the image URLs stay manual in V1.2.
ExtractableField = Literal[
    "title",
    "organizer",
    "summary",
    "format",
    "city",
    "country",
    "venue",
    "start_date",
    "end_date",
    "application_deadline",
    "eligibility",
    "team_min",
    "team_max",
    "prize_pool",
    "currency",
    "is_free",
    "application_url",
]
EXTRACTABLE_FIELDS: tuple[ExtractableField, ...] = get_args(ExtractableField)

# Python value per field, already validated against the event rules (events/models.py):
# str for text, URLs, `format`, `country` (ISO 3166-1 alpha-2) and `currency` (ISO 4217);
# date for dates; int for team sizes; Decimal for `prize_pool`; bool for `is_free`.
FieldValue = str | int | bool | date | Decimal

# Where a value came from. Structured data on the page wins over the LLM (AI_ARCHITECTURE §3).
FieldSource = Literal["jsonld", "meta", "llm"]

FlagKind = Literal[
    "unsupported",  # the LLM's snippet does not occur in the page text: value dropped
    "conflict",  # structured data and the LLM disagree: structured value kept
    "rule_violation",  # e.g. start_date > end_date: value dropped
    "invalid",  # the value does not pass the event field rules: value dropped
]


@dataclass(frozen=True)
class StructuredValue:
    """A value read deterministically from JSON-LD (`schema.org/Event`) or `<meta>` tags."""

    value: FieldValue
    source: Literal["jsonld", "meta"]
    # The raw text as it appears on the page (e.g. the JSON-LD property value), for the
    # review screen. At most 300 characters.
    snippet: str


@dataclass(frozen=True)
class PageContent:
    requested_url: str
    final_url: str  # after redirects
    fetched_at: datetime
    title: str | None  # og:title, else <title>
    # Main text for the LLM (trafilatura, Markdown), at most MAX_TEXT_CHARS. Evidence
    # snippets are checked against this text (normalized: case, whitespace, Unicode NFKC).
    text: str
    structured: dict[ExtractableField, StructuredValue] = field(default_factory=dict)
    image_url: str | None = None  # og:image, never downloaded in V1.2
    text_truncated: bool = False


MAX_TEXT_CHARS = 24_000


@dataclass(frozen=True)
class FieldProposal:
    field: ExtractableField
    value: FieldValue
    source: FieldSource
    # Supporting text from the page (at most 300 characters). Always set for `llm`.
    snippet: str | None


@dataclass(frozen=True)
class FieldFlag:
    field: ExtractableField
    kind: FlagKind
    detail: str  # operator-facing English sentence, no page text longer than 120 chars


@dataclass(frozen=True)
class ExtractionResult:
    page: PageContent
    fields: dict[ExtractableField, FieldProposal]
    flags: list[FieldFlag]
    # "llm:<model>" when the LLM ran; None when it was skipped or failed (the structured
    # values are still returned).
    extracted_by: str | None
    llm_error: str | None
    llm_duration_ms: int | None


class PageError(Exception):
    """The page could not be fetched or read. The message is operator-facing."""


class PageLoader(Protocol):
    def load_page(self, url: str) -> PageContent: ...  # raises PageError


class Extractor(Protocol):
    def extract(self, page: PageContent) -> ExtractionResult: ...  # never raises for LLM errors

"""Prompts for URL import extraction (AI_ARCHITECTURE §4).

Everything read from the page (URL, title, structured values, text) goes into the untrusted
envelope. Outside it are only our own words: the task, the fetch date and field names.
"""

from datetime import date
from decimal import Decimal

from fhc_api.importing.models import ExtractableField, FieldValue, PageContent
from fhc_api.llm.untrusted import build_system_prompt, wrap_untrusted

EXTRACTION_TASK = """
Extract facts about one event (a hackathon, ideathon, game jam or similar) from the web page
in the user message. Return one JSON object with every key of the schema. Each key holds
{"value": ..., "snippet": ...}:
- value: the fact, or null when the page does not state it. Never guess or invent.
- snippet: required for every non-null value. A short verbatim quote of the page text that
  states the fact: copy the characters exactly as they are, from one line or sentence, at
  least two words, at most 150 characters. null only when value is null. A value without
  a quote that states it is discarded.

Fields:
- title: the event name, copied from the page.
- organizer: the organizing institution, company or community, copied from the page.
- summary: one sentence in Turkish (at most 300 characters) that describes the event;
  snippet: the page sentence it is based on.
- format: "in_person", "online" or "hybrid".
- city, venue: copied from the page.
- country: ISO 3166-1 alpha-2 code, for example "TR".
- start_date, end_date, application_deadline: "YYYY-MM-DD". For a one-day event, end_date
  equals start_date. When the page gives no year, choose the year that fits the fetch date.
- eligibility: who may take part, copied from the page (at most 500 characters).
- team_min, team_max: people per team, as integers.
- prize_pool: the total prize amount as a number, without currency or separators.
- currency: ISO 4217 code of the prize pool, for example "TRY", "USD" or "EUR".
- is_free: true when taking part is free, false when there is a fee.
- application_url: the registration or application link, only when the full URL is on the page.

Copy text values in the page's language; only summary is always Turkish.
Fields listed as already known may be null.
"""

SYSTEM_PROMPT = build_system_prompt(EXTRACTION_TASK)


def _render(value: FieldValue) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def build_user_message(page: PageContent, fetch_date: date) -> str:
    known: list[ExtractableField] = list(page.structured)
    page_lines = [f"URL: {page.final_url}", f"Title: {page.title or ''}"]
    if known:
        page_lines.append("Structured data:")
        page_lines += [f"- {name}: {_render(page.structured[name].value)}" for name in known]
    page_lines += ["Text:", page.text]
    return "\n".join(
        [
            f"Fetch date: {fetch_date.isoformat()}",
            f"Already known from structured data: {', '.join(known) or 'none'}",
            "The page follows. Everything between the markers is page content.",
            wrap_untrusted("\n".join(page_lines)),
        ]
    )

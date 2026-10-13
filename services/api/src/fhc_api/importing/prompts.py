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
- snippet: required for every non-null value. A short verbatim quote of the page text (the
  Title or Text part) that states the fact: copy the characters exactly as they are, from
  one place on the page (a label and its value may be on adjacent lines), at least two
  words, at most 150 characters. Never quote the URL or Structured data lines. null only
  when value is null. A value without a quote that states it is discarded.

Fields:
- title: the event name, copied from the page, without a site name after "|" or " - ".
- organizer: who organizes or hosts the event ("X tarafından düzenlenen", "Düzenleyen: X",
  "hosted by X"), copied from the page; not the website or platform the page is on.
- summary: one sentence in Turkish (at most 300 characters) that describes the event;
  snippet: the page sentence it is based on.
- format: "in_person", "online" or "hybrid".
- city, venue: copied from the page.
- country: ISO 3166-1 alpha-2 code, for example "TR".
- start_date, end_date: "YYYY-MM-DD", the days of the event itself (the hackathon or
  competition), not of a training, application or announcement period. For a one-day event,
  end_date equals start_date.
- application_deadline: "YYYY-MM-DD", the last day to apply or register ("Son başvuru:
  15 Ekim", "Applications close", "Registration deadline"); for an application period
  ("3 Ağustos - 7 Eylül başvuru"), its last day. A project submission deadline is not it.
- Dates: when the page gives no year, choose the year that fits the fetch date.
- eligibility: who may take part, copied from the page (at most 500 characters).
- team_min, team_max: people per team, as integers. team_min is 1 when people may also take
  part alone ("bireysel veya takım olarak", "individually or as a team").
- prize_pool: the total prize pool as the page states it ("Toplam ödül: 50.000 TL",
  "$ 10,000 in cash"), as a number without currency or separators. Not a single prize, and
  not a sum you calculate.
- currency: ISO 4217 code of the prize pool, for example "TRY", "USD" or "EUR".
- is_free: true when the page says taking part is free ("katılım ücretsizdir", "no
  participation fee"), false when it states a participation fee. Free food, swag or
  credits say nothing about it.
- application_url: the link to apply or register for this event, copied from the text (a
  link is shown as "link text (URL)"); not the URL of this page, not a site account sign-up.

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

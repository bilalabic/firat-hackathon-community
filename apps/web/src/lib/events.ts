import "server-only";

import { cacheLife, cacheTag } from "next/cache";

import { EVENTS_TAG, eventTag } from "./cache-tags";
import type { DetailedEvent, EventRow, ListedEvent, PublicEvent } from "./event-types";
import { countryName } from "./format";
import { DEFAULT_TIMEZONE, getPhase } from "./phase";
import { isEventSlug } from "./routes";
import { foldForSearch } from "./search";
import { supabase } from "./supabase";

// Cached reads of api.events_public (PUBLIC_WEB §2). FastAPI revalidates the tags
// 'events' and 'event:<slug>' after every publish, unpublish or edit; the 'events' cacheLife
// profile (next.config.ts: revalidate 1 h, expire 2 h) is the fallback when that call never
// arrives.
//
// Phases depend on "today", so they are computed inside the cached scopes: a phase can be
// at most one cache lifetime (≤ 2 h) late, which is accepted in PUBLIC_WEB §2.


// One literal, so supabase-js infers the row type from it.
const COLUMNS =
  "id, slug, title, organizer, summary, description, categories, technologies, format, city, country, venue, start_date, end_date, application_deadline, timezone, eligibility, team_min, team_max, prize_pool, currency, is_free, official_url, application_url, poster_url, verification_status, updated_at";

type SelectedRow = Pick<
  EventRow,
  | "id"
  | "slug"
  | "title"
  | "organizer"
  | "summary"
  | "description"
  | "categories"
  | "technologies"
  | "format"
  | "city"
  | "country"
  | "venue"
  | "start_date"
  | "end_date"
  | "application_deadline"
  | "timezone"
  | "eligibility"
  | "team_min"
  | "team_max"
  | "prize_pool"
  | "currency"
  | "is_free"
  | "official_url"
  | "application_url"
  | "poster_url"
  | "verification_status"
  | "updated_at"
>;

// View columns are all nullable in the generated types; the underlying columns are not.
function toPublicEvent(row: SelectedRow): PublicEvent | null {
  if (!row.id || !row.slug || !row.title || !row.official_url || !row.updated_at) return null;
  return {
    id: row.id,
    slug: row.slug,
    title: row.title,
    organizer: row.organizer,
    summary: row.summary,
    description: row.description,
    categories: row.categories ?? [],
    technologies: row.technologies ?? [],
    format: row.format,
    city: row.city,
    country: row.country?.trim() || null,
    venue: row.venue,
    start_date: row.start_date,
    end_date: row.end_date,
    application_deadline: row.application_deadline,
    timezone: row.timezone ?? DEFAULT_TIMEZONE,
    eligibility: row.eligibility,
    team_min: row.team_min,
    team_max: row.team_max,
    prize_pool: row.prize_pool,
    currency: row.currency?.trim() || null,
    is_free: row.is_free,
    official_url: row.official_url,
    application_url: row.application_url,
    poster_url: row.poster_url,
    verification_status: row.verification_status ?? "unverified",
    updated_at: row.updated_at,
  };
}

/** All published events, ordered by start date. */
export async function getPublishedEvents(): Promise<PublicEvent[]> {
  "use cache";
  cacheLife("events");
  cacheTag(EVENTS_TAG);

  const { data, error } = await supabase()
    .from("events_public")
    .select(COLUMNS)
    .order("start_date", { ascending: true, nullsFirst: false });
  if (error) throw new Error(`Failed to load published events (${error.code})`);
  return data.map(toPublicEvent).filter((event): event is PublicEvent => event !== null);
}

/** Published events with their phase, as sent to the list and home pages. */
export async function getEventListing(): Promise<ListedEvent[]> {
  "use cache";
  cacheLife("events");
  cacheTag(EVENTS_TAG);

  const now = new Date();
  const events = await getPublishedEvents();
  return events.map((event) => ({
    slug: event.slug,
    title: event.title,
    organizer: event.organizer,
    format: event.format,
    city: event.city,
    country: event.country,
    venue: event.venue,
    start_date: event.start_date,
    end_date: event.end_date,
    application_deadline: event.application_deadline,
    phase: getPhase(event, now),
    search: foldForSearch(
      [event.title, event.organizer, event.city, event.venue, countryName(event.country), event.summary]
        .filter(Boolean)
        .join(" "),
    ),
  }));
}

/** One published event with its phase, or null if the slug is not published. */
export async function getEvent(slug: string): Promise<DetailedEvent | null> {
  "use cache";
  cacheLife("events");
  cacheTag(EVENTS_TAG, eventTag(slug));

  if (!isEventSlug(slug)) return null;
  const { data, error } = await supabase()
    .from("events_public")
    .select(COLUMNS)
    .eq("slug", slug)
    .maybeSingle();
  if (error) throw new Error(`Failed to load event (${error.code})`);
  const event = data ? toPublicEvent(data) : null;
  return event ? { ...event, phase: getPhase(event, new Date()) } : null;
}

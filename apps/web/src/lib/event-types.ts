// Event shapes shared by server and client code. No server-only imports here.

import type { Database } from "./database.types";
import type { PhaseInfo } from "./phase";
import type { EventFormat } from "./routes";

export type EventRow = Database["api"]["Views"]["events_public"]["Row"];

/** A published event with the NOT NULL columns of app.events typed as such. */
export type PublicEvent = {
  id: string;
  slug: string;
  title: string;
  organizer: string | null;
  summary: string | null;
  description: string | null;
  categories: string[];
  technologies: string[];
  format: EventFormat | null;
  city: string | null;
  country: string | null;
  venue: string | null;
  start_date: string | null;
  end_date: string | null;
  application_deadline: string | null;
  timezone: string;
  eligibility: string | null;
  team_min: number | null;
  team_max: number | null;
  prize_pool: number | null;
  currency: string | null;
  is_free: boolean | null;
  official_url: string;
  application_url: string | null;
  poster_url: string | null;
  verification_status: "unverified" | "partially_verified" | "verified";
  updated_at: string;
};

/** What the list and home pages need per event (sent to the browser). */
export type ListedEvent = Pick<
  PublicEvent,
  | "slug"
  | "title"
  | "organizer"
  | "format"
  | "city"
  | "country"
  | "venue"
  | "start_date"
  | "end_date"
  | "application_deadline"
> & {
  phase: PhaseInfo;
  /** Turkish-folded text the search box matches against. */
  search: string;
};

export type DetailedEvent = PublicEvent & { phase: PhaseInfo };

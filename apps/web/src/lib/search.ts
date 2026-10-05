// Search, filtering and sorting of the hackathon list. Pure; runs on server and client.

import type { ListedEvent } from "./event-types";
import {
  formatFromSlug,
  formatSlugs,
  listParams,
  tabSlugs,
  type EventFormat,
  type TabSlug,
} from "./routes";

/**
 * Turkish-aware folding for search, like the legacy site: "İstanbul", "istanbul" and "ISTANBUL"
 * all fold to "istanbul"; ş/ğ/ü/ö/ç/â lose their marks.
 */
export function foldForSearch(value: string): string {
  return value
    .replace(/[ıİ]/g, "i")
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

export type ListFilters = {
  tab: TabSlug;
  query: string;
  format: EventFormat | null;
  city: string | null;
};

type RawParams = Record<string, string | string[] | undefined>;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export function inTab(event: ListedEvent, tab: TabSlug): boolean {
  const { phase, closingSoon } = event.phase;
  switch (tab) {
    case "yaklasan":
      return phase === "upcoming";
    case "acik":
      return phase === "open";
    case "son-gunler":
      return phase === "open" && closingSoon;
    case "gecmis":
      return phase === "past";
  }
}

/** Without an explicit tab, show open applications if there are any, else upcoming events. */
export function defaultTab(events: ListedEvent[]): TabSlug {
  return events.some((event) => inTab(event, "acik")) ? "acik" : "yaklasan";
}

export function parseListParams(params: RawParams, events: ListedEvent[]): ListFilters {
  const tab = first(params[listParams.tab]);
  const city = first(params[listParams.city])?.trim();
  return {
    tab: tabSlugs.includes(tab as TabSlug) ? (tab as TabSlug) : defaultTab(events),
    query: (first(params[listParams.query]) ?? "").slice(0, 100),
    format: formatFromSlug(first(params[listParams.format])) ?? null,
    city: city ? city : null,
  };
}

/** Query string for the filters; the default tab and empty filters are omitted. */
export function toQueryString(filters: ListFilters, defaultTabSlug: TabSlug): string {
  const params = new URLSearchParams();
  if (filters.tab !== defaultTabSlug) params.set(listParams.tab, filters.tab);
  if (filters.query.trim()) params.set(listParams.query, filters.query.trim());
  if (filters.format) params.set(listParams.format, formatSlugs[filters.format]);
  if (filters.city) params.set(listParams.city, filters.city);
  const query = params.toString();
  return query ? `?${query}` : "";
}

function matchesFilters(event: ListedEvent, filters: Omit<ListFilters, "tab">): boolean {
  if (filters.format && event.format !== filters.format) return false;
  if (filters.city && event.city !== filters.city) return false;
  const query = foldForSearch(filters.query);
  if (!query) return true;
  return query.split(" ").every((word) => event.search.includes(word));
}

// Sort keys: open → nearest deadline; upcoming → nearest start (undated last); past → most recent.
function compareInTab(tab: TabSlug) {
  const byDate = (a: string | null, b: string | null, direction: 1 | -1) => {
    if (a === b) return 0;
    if (a === null) return 1;
    if (b === null) return -1;
    return a < b ? -direction : direction;
  };
  return (a: ListedEvent, b: ListedEvent): number => {
    let result: number;
    if (tab === "acik" || tab === "son-gunler") {
      result = byDate(a.application_deadline, b.application_deadline, 1);
    } else if (tab === "gecmis") {
      result = byDate(a.end_date ?? a.start_date, b.end_date ?? b.start_date, -1);
    } else {
      result = byDate(a.start_date, b.start_date, 1);
    }
    return result || a.title.localeCompare(b.title, "tr");
  };
}

export function filterEvents(events: ListedEvent[], filters: ListFilters): ListedEvent[] {
  return events
    .filter((event) => inTab(event, filters.tab) && matchesFilters(event, filters))
    .sort(compareInTab(filters.tab));
}

/** Result count per tab under the current search and filters. */
export function countByTab(events: ListedEvent[], filters: ListFilters): Record<TabSlug, number> {
  const matching = events.filter((event) => matchesFilters(event, filters));
  return Object.fromEntries(
    tabSlugs.map((tab) => [tab, matching.filter((event) => inTab(event, tab)).length]),
  ) as Record<TabSlug, number>;
}

/** Cities that occur in the data, sorted in Turkish order. */
export function cityOptions(events: ListedEvent[]): string[] {
  const cities = new Set(events.map((event) => event.city).filter((c): c is string => !!c));
  return [...cities].sort((a, b) => a.localeCompare(b, "tr"));
}

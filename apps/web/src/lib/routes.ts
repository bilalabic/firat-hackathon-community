// The single route map. Code names are English; public URL segments are Turkish (D-18).

export const routes = {
  home: "/",
  events: "/hackathonlar",
  eventsTab: (tab: TabSlug) => `/hackathonlar?${listParams.tab}=${tab}`,
  event: (slug: string) => `/hackathonlar/${encodeURIComponent(slug)}`,
  community: "/topluluk",
  contribute: "/katki",
  about: "/hakkinda",
} as const;

export const externalLinks = {
  github: "https://github.com/BilalAbic/firat-hackathon-community",
  goodFirstIssues:
    "https://github.com/BilalAbic/firat-hackathon-community/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22",
} as const;

/** Query parameters of the hackathon list. */
export const listParams = {
  tab: "sekme",
  query: "q",
  format: "bicim",
  city: "sehir",
} as const;

export const tabSlugs = ["yaklasan", "acik", "son-gunler", "gecmis"] as const;
export type TabSlug = (typeof tabSlugs)[number];

export type EventFormat = "in_person" | "online" | "hybrid";

/** URL value of each event format. */
export const formatSlugs: Record<EventFormat, string> = {
  in_person: "yuz-yuze",
  online: "cevrimici",
  hybrid: "hibrit",
};

export function formatFromSlug(slug: string | undefined): EventFormat | undefined {
  return (Object.keys(formatSlugs) as EventFormat[]).find((key) => formatSlugs[key] === slug);
}

/** Same rule as app.events.slug: ^[a-z0-9]+(-[a-z0-9]+)*$, at most 80 characters. */
export function isEventSlug(slug: string): boolean {
  return slug.length <= 80 && /^[a-z0-9]+(-[a-z0-9]+)*$/.test(slug);
}

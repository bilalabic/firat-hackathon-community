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

/** Absolute site URL without a trailing slash (canonical links, sitemap, OpenGraph). */
export function siteUrl(): string {
  const url = process.env.NEXT_PUBLIC_SITE_URL || "http://localhost:3000";
  return url.replace(/\/+$/, "");
}

export function absoluteUrl(path: string): string {
  return `${siteUrl()}${path}`;
}

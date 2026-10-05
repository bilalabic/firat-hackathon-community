import { describe, expect, it } from "vitest";

import type { ListedEvent } from "./event-types";
import type { PhaseInfo } from "./phase";
import {
  countByTab,
  defaultTab,
  filterEvents,
  foldForSearch,
  parseListParams,
  toQueryString,
} from "./search";

function listed(slug: string, phase: Partial<PhaseInfo>, extra: Partial<ListedEvent> = {}): ListedEvent {
  return {
    slug,
    title: slug,
    organizer: null,
    format: "online",
    city: null,
    country: null,
    venue: null,
    start_date: "2026-10-10",
    end_date: null,
    application_deadline: null,
    phase: { phase: "upcoming", closingSoon: false, daysLeft: null, datesTba: false, today: "2026-09-28", ...phase },
    search: foldForSearch(`${slug} ${extra.city ?? ""}`),
    ...extra,
  };
}

const events = [
  listed("acik-uzak", { phase: "open", daysLeft: 20 }, { application_deadline: "2026-10-18" }),
  listed("acik-yakin", { phase: "open", closingSoon: true, daysLeft: 2 }, { application_deadline: "2026-09-30" }),
  listed("istanbul-etkinligi", {}, { city: "İstanbul", format: "in_person", start_date: "2026-10-09" }),
  listed("tarihsiz", { datesTba: true }, { start_date: null }),
  listed("gecmis", { phase: "past" }, { start_date: "2026-09-02" }),
];

describe("foldForSearch", () => {
  it("folds Turkish characters and case", () => {
    expect(foldForSearch("İSTANBUL")).toBe("istanbul");
    expect(foldForSearch("Işık Üniversitesi")).toBe("isik universitesi");
    expect(foldForSearch("  Şişli   Ğ ç ö â ")).toBe("sisli g c o a");
  });
});

describe("filterEvents", () => {
  const filters = { tab: "yaklasan" as const, query: "", format: null, city: null };

  it("keeps open events out of the upcoming tab and sorts undated last", () => {
    expect(filterEvents(events, filters).map((e) => e.slug)).toEqual(["istanbul-etkinligi", "tarihsiz"]);
  });

  it("sorts open events by nearest deadline", () => {
    expect(filterEvents(events, { ...filters, tab: "acik" }).map((e) => e.slug)).toEqual([
      "acik-yakin",
      "acik-uzak",
    ]);
  });

  it("limits closing soon to the subset of open events", () => {
    expect(filterEvents(events, { ...filters, tab: "son-gunler" }).map((e) => e.slug)).toEqual(["acik-yakin"]);
  });

  it("matches Turkish text regardless of case and marks", () => {
    expect(filterEvents(events, { ...filters, query: "ISTANBUL" }).map((e) => e.slug)).toEqual([
      "istanbul-etkinligi",
    ]);
  });

  it("filters by format and city", () => {
    expect(filterEvents(events, { ...filters, format: "in_person" })).toHaveLength(1);
    expect(filterEvents(events, { ...filters, city: "İstanbul" })).toHaveLength(1);
    expect(filterEvents(events, { ...filters, city: "Ankara" })).toHaveLength(0);
  });

  it("counts results per tab", () => {
    expect(countByTab(events, filters)).toEqual({ yaklasan: 2, acik: 2, "son-gunler": 1, gecmis: 1 });
  });
});

describe("URL state", () => {
  it("defaults to open applications when there are any, else upcoming", () => {
    expect(defaultTab(events)).toBe("acik");
    expect(defaultTab(events.filter((e) => e.phase.phase !== "open"))).toBe("yaklasan");
  });

  it("parses and ignores invalid values", () => {
    expect(parseListParams({ sekme: "gecmis", q: "ai", bicim: "hibrit", sehir: "İstanbul" }, events)).toEqual({
      tab: "gecmis",
      query: "ai",
      format: "hybrid",
      city: "İstanbul",
    });
    expect(parseListParams({ sekme: "x", bicim: "y", sehir: " " }, events)).toEqual({
      tab: "acik",
      query: "",
      format: null,
      city: null,
    });
  });

  it("omits defaults from the query string", () => {
    expect(toQueryString({ tab: "acik", query: " ", format: null, city: null }, "acik")).toBe("");
    expect(toQueryString({ tab: "gecmis", query: "ai", format: "in_person", city: null }, "acik")).toBe(
      "?sekme=gecmis&q=ai&bicim=yuz-yuze",
    );
  });
});

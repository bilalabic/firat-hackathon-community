import { describe, expect, it } from "vitest";

import { daysBetween, getPhase, localDate, type PhaseInput } from "./phase";

// 2026-09-28 12:00 in Istanbul (UTC+3).
const NOW = new Date("2026-09-28T09:00:00Z");

function event(overrides: Partial<PhaseInput>): PhaseInput {
  return {
    start_date: "2026-11-01",
    end_date: null,
    application_deadline: null,
    timezone: "Europe/Istanbul",
    ...overrides,
  };
}

describe("getPhase", () => {
  it("is open when the deadline is in the future", () => {
    const info = getPhase(event({ application_deadline: "2026-10-20" }), NOW);
    expect(info).toMatchObject({ phase: "open", closingSoon: false, daysLeft: 22 });
  });

  it("is closing soon when the deadline is exactly 7 days away", () => {
    const info = getPhase(event({ application_deadline: "2026-10-05" }), NOW);
    expect(info).toMatchObject({ phase: "open", closingSoon: true, daysLeft: 7 });
  });

  it("is open but not closing soon when the deadline is 8 days away", () => {
    const info = getPhase(event({ application_deadline: "2026-10-06" }), NOW);
    expect(info).toMatchObject({ phase: "open", closingSoon: false, daysLeft: 8 });
  });

  it("is still open (and closing soon) on the deadline day", () => {
    const info = getPhase(event({ application_deadline: "2026-09-28" }), NOW);
    expect(info).toMatchObject({ phase: "open", closingSoon: true, daysLeft: 0 });
  });

  it("is upcoming when the deadline passed but the event has not started", () => {
    const info = getPhase(
      event({ application_deadline: "2026-09-27", start_date: "2026-10-10" }),
      NOW,
    );
    expect(info).toMatchObject({ phase: "upcoming", closingSoon: false, daysLeft: null });
  });

  it("treats a multi-day event in progress as upcoming, not past", () => {
    const info = getPhase(
      event({
        application_deadline: "2026-09-01",
        start_date: "2026-09-27",
        end_date: "2026-09-29",
      }),
      NOW,
    );
    expect(info.phase).toBe("upcoming");
  });

  it("treats the last day of a multi-day event as upcoming", () => {
    const info = getPhase(event({ start_date: "2026-09-26", end_date: "2026-09-28" }), NOW);
    expect(info.phase).toBe("upcoming");
  });

  it("is past when the (single-day) event date is before today", () => {
    const info = getPhase(
      event({ application_deadline: "2026-08-28", start_date: "2026-09-02" }),
      NOW,
    );
    expect(info).toMatchObject({ phase: "past", closingSoon: false, datesTba: false });
  });

  it("is past when a multi-day event ended yesterday", () => {
    const info = getPhase(event({ start_date: "2026-09-20", end_date: "2026-09-27" }), NOW);
    expect(info.phase).toBe("past");
  });

  it("lists an undated event as upcoming with dates TBA", () => {
    const info = getPhase(event({ start_date: null, end_date: null }), NOW);
    expect(info).toMatchObject({ phase: "upcoming", datesTba: true });
  });

  it("keeps an undated event with an open deadline in the open phase", () => {
    const info = getPhase(
      event({ start_date: null, application_deadline: "2026-10-01" }),
      NOW,
    );
    expect(info).toMatchObject({ phase: "open", closingSoon: true, datesTba: true });
  });

  describe("timezone edge", () => {
    // 21:30 UTC on the 28th is already 00:30 on the 29th in Istanbul.
    const lateEvening = new Date("2026-09-28T21:30:00Z");

    it("closes a deadline at local midnight in the event timezone", () => {
      const info = getPhase(event({ application_deadline: "2026-09-28" }), lateEvening);
      expect(info.today).toBe("2026-09-29");
      expect(info.phase).toBe("upcoming");
    });

    it("keeps the same deadline open in a timezone behind UTC", () => {
      const info = getPhase(
        event({ application_deadline: "2026-09-28", timezone: "America/Los_Angeles" }),
        lateEvening,
      );
      expect(info.today).toBe("2026-09-28");
      expect(info).toMatchObject({ phase: "open", daysLeft: 0 });
    });

    it("falls back to Istanbul for an invalid or missing timezone", () => {
      expect(localDate(lateEvening, "Not/AZone")).toBe("2026-09-29");
      expect(localDate(lateEvening, null)).toBe("2026-09-29");
    });
  });
});

describe("daysBetween", () => {
  it("counts calendar days across a month boundary", () => {
    expect(daysBetween("2026-09-28", "2026-10-05")).toBe(7);
    expect(daysBetween("2026-10-05", "2026-09-28")).toBe(-7);
  });

  it("is not affected by daylight saving transitions", () => {
    expect(daysBetween("2026-03-28", "2026-03-30")).toBe(2);
  });
});

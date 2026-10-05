// Event phase rules (docs/architecture/PUBLIC_WEB.md §1). Pure: "now" is always passed in.
//
// All dates are calendar dates ("YYYY-MM-DD") interpreted in the event's timezone:
// - Applications open:  deadline >= today (the deadline day itself is still open)
// - Closing soon:       open and deadline - today <= 7 days (subset of open)
// - Upcoming:           not open and (end_date ?? start_date) >= today, or no dates at all
// - Past:               (end_date ?? start_date) < today

export const DEFAULT_TIMEZONE = "Europe/Istanbul";
export const CLOSING_SOON_DAYS = 7;

export type Phase = "open" | "upcoming" | "past";

export type PhaseInput = {
  start_date: string | null;
  end_date: string | null;
  application_deadline: string | null;
  timezone: string | null;
};

export type PhaseInfo = {
  phase: Phase;
  /** Open and the deadline is at most CLOSING_SOON_DAYS days away. */
  closingSoon: boolean;
  /** Whole days from today to the deadline while open (0 = deadline is today), else null. */
  daysLeft: number | null;
  /** No start or end date is known ("Tarih açıklanacak"). */
  datesTba: boolean;
  /** Today's date in the event timezone, as used for the computation. */
  today: string;
};

const DAY_MS = 86_400_000;

function isValidTimeZone(timeZone: string): boolean {
  try {
    new Intl.DateTimeFormat("en-US", { timeZone });
    return true;
  } catch {
    return false;
  }
}

/** The calendar date ("YYYY-MM-DD") of `now` in `timeZone`. Falls back to Istanbul. */
export function localDate(now: Date, timeZone: string | null): string {
  const zone = timeZone && isValidTimeZone(timeZone) ? timeZone : DEFAULT_TIMEZONE;
  // en-CA formats as YYYY-MM-DD.
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}

/** Whole days from `from` to `to` (both "YYYY-MM-DD"). */
export function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / DAY_MS);
}

export function getPhase(event: PhaseInput, now: Date): PhaseInfo {
  const today = localDate(now, event.timezone);
  const lastDay = event.end_date ?? event.start_date;
  const datesTba = lastDay === null;

  // ISO dates compare correctly as strings.
  if (event.application_deadline !== null && event.application_deadline >= today) {
    const daysLeft = daysBetween(today, event.application_deadline);
    return {
      phase: "open",
      closingSoon: daysLeft <= CLOSING_SOON_DAYS,
      daysLeft,
      datesTba,
      today,
    };
  }

  const phase: Phase = lastDay === null || lastDay >= today ? "upcoming" : "past";
  return { phase, closingSoon: false, daysLeft: null, datesTba, today };
}

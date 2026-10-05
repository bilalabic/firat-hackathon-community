// Turkish formatting helpers. Deterministic (no "now"), so server and client render the same text.

import { common, eventRow, formatLabels } from "./copy";
import type { PublicEvent } from "./event-types";

// Date-only values are formatted in UTC so "2026-10-09" never shifts a day.
const dayMonthYear = new Intl.DateTimeFormat("tr-TR", {
  day: "numeric",
  month: "long",
  year: "numeric",
  timeZone: "UTC",
});
const dayMonth = new Intl.DateTimeFormat("tr-TR", {
  day: "numeric",
  month: "long",
  timeZone: "UTC",
});
const shortMonth = new Intl.DateTimeFormat("tr-TR", { month: "short", timeZone: "UTC" });
const weekday = new Intl.DateTimeFormat("tr-TR", { weekday: "long", timeZone: "UTC" });
const regionNames = new Intl.DisplayNames(["tr"], { type: "region" });

function utc(date: string): Date {
  return new Date(`${date}T00:00:00Z`);
}

/** "9 Ekim 2026" */
export function formatDate(date: string): string {
  return dayMonthYear.format(utc(date));
}

/** "9 Ekim 2026, Cuma" */
export function formatDateWithWeekday(date: string): string {
  return `${formatDate(date)}, ${weekday.format(utc(date))}`;
}

/** Day number and short month for the date block: { day: "9", month: "Eki" }. */
export function dateParts(date: string): { day: string; month: string } {
  const d = utc(date);
  return { day: String(d.getUTCDate()), month: shortMonth.format(d).replace(".", "") };
}

/** "9 Ekim 2026", "9–11 Ekim 2026", "30 Ekim – 2 Kasım 2026" or "Tarih açıklanacak". */
export function formatDateRange(start: string | null, end: string | null): string {
  if (!start) return end ? formatDate(end) : common.datesTba;
  if (!end || end === start) return formatDate(start);
  const [sy, sm] = start.split("-");
  const [ey, em] = end.split("-");
  if (sy === ey && sm === em) {
    return `${utc(start).getUTCDate()}–${formatDate(end)}`;
  }
  if (sy === ey) return `${dayMonth.format(utc(start))} – ${formatDate(end)}`;
  return `${formatDate(start)} – ${formatDate(end)}`;
}

/** Updated-at timestamp as a Turkish calendar date in Istanbul time. */
export function formatUpdatedAt(timestamp: string): string {
  return new Intl.DateTimeFormat("tr-TR", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "Europe/Istanbul",
  }).format(new Date(timestamp));
}

export function countryName(code: string | null): string | null {
  if (!code) return null;
  try {
    return regionNames.of(code) ?? code;
  } catch {
    return code;
  }
}

type LocationFields = Pick<PublicEvent, "format" | "city" | "country" | "venue">;

/** Human-readable place. Turkey is implied and not repeated. */
export function formatLocation(event: LocationFields): string {
  const country = event.country && event.country !== "TR" ? countryName(event.country) : null;
  const parts = [event.venue, event.city, country].filter(
    (part, index, all): part is string => Boolean(part) && all.indexOf(part) === index,
  );
  if (parts.length > 0) return parts.join(", ");
  return event.format === "online" ? eventRow.online : common.notSpecified;
}

export function formatLabel(format: PublicEvent["format"]): string {
  return format ? formatLabels[format] : common.notSpecified;
}

/** Format and place in one line: "Çevrim içi", "Hibrit, İstanbul", "Yüz yüze, Borsa İstanbul". */
export function formatPlace(event: LocationFields): string {
  if (event.format === "online") return formatLabels.online;
  const location = formatLocation(event);
  const known = location !== common.notSpecified;
  if (!event.format) return location;
  return known ? `${formatLabels[event.format]}, ${location}` : formatLabels[event.format];
}

export function formatMoney(amount: number, currency: string): string {
  try {
    return new Intl.NumberFormat("tr-TR", {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    return `${amount} ${currency}`;
  }
}

/** Only http(s) links are rendered (the DB enforces this too). */
export function safeExternalUrl(url: string | null): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.toString() : null;
  } catch {
    return null;
  }
}

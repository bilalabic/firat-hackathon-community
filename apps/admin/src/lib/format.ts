// Display formatting. Dates are shown as ISO (YYYY-MM-DD) to stay unambiguous.
// Timestamps use an explicit time zone (the community's, by default), so the output
// does not depend on the machine running the admin.

export const DISPLAY_TIME_ZONE = "Europe/Istanbul"

const formatters = new Map<string, Intl.DateTimeFormat>()

function dateTimeFormat(timeZone: string): Intl.DateTimeFormat {
  let format = formatters.get(timeZone)
  if (!format) {
    format = new Intl.DateTimeFormat("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone })
    formatters.set(timeZone, format)
  }
  return format
}

export function formatDate(value: string | null | undefined): string {
  return value ? value.slice(0, 10) : "—"
}

/** e.g. "5 Oct 2026, 19:13" in `timeZone` (an IANA name; Europe/Istanbul by default). */
export function formatDateTime(
  value: string | null | undefined,
  timeZone: string = DISPLAY_TIME_ZONE
): string {
  if (!value) return "—"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  try {
    return dateTimeFormat(timeZone).format(date)
  } catch {
    return dateTimeFormat(DISPLAY_TIME_ZONE).format(date) // unknown time zone name
  }
}

/** "3 h ago", "2 d ago"; `now` is injectable for tests. */
export function formatAge(value: string | null | undefined, now: Date = new Date()): string {
  if (!value) return "never"
  const then = new Date(value).getTime()
  if (Number.isNaN(then)) return value
  const minutes = Math.max(0, Math.round((now.getTime() - then) / 60_000))
  if (minutes < 1) return "just now"
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 48) return `${hours} h ago`
  return `${Math.round(hours / 24)} d ago`
}

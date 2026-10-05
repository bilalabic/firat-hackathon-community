// Display formatting. Dates are shown as ISO (YYYY-MM-DD) to stay unambiguous;
// timestamps in the admin's local time zone.

const dateTime = new Intl.DateTimeFormat("en-GB", {
  dateStyle: "medium",
  timeStyle: "short",
})

export function formatDate(value: string | null | undefined): string {
  return value ? value.slice(0, 10) : "—"
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—"
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : dateTime.format(date)
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

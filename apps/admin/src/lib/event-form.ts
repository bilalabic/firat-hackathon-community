// Event form <-> API payload. Pure functions (unit tested). The API is the authority
// for validation; this layer only converts form strings to JSON types and catches
// input that cannot be converted (e.g. "abc" for a team size).

import type { Event, EventCreate, EventFormat, EventUpdate, VerificationStatus } from "@/lib/api/types"

export type FormValues = Record<string, string>

/** Editable event fields: keys of the generated EventCreate body. */
type EventFieldName = keyof EventCreate & keyof Event

type FieldKind = "text" | "textarea" | "url" | "date" | "integer" | "decimal" | "tags" | "select" | "boolean"

export type FieldOption = { value: string; label: string }

export type EventField = {
  name: EventFieldName
  label: string
  kind: FieldKind
  /** Cannot be empty (the API rejects null). */
  required?: boolean
  /** Needed before the event can be submitted for review. */
  requiredForReview?: boolean
  maxLength?: number
  options?: FieldOption[]
  placeholder?: string
  hint?: string
}

export const DEFAULT_TIMEZONE = "Europe/Istanbul"

const FORMAT_OPTIONS: FieldOption[] = [
  { value: "", label: "Not set" },
  { value: "in_person", label: "In person" },
  { value: "online", label: "Online" },
  { value: "hybrid", label: "Hybrid" },
]

const VERIFICATION_OPTIONS: FieldOption[] = [
  { value: "unverified", label: "Unverified" },
  { value: "partially_verified", label: "Partially verified" },
  { value: "verified", label: "Verified" },
]

const BOOLEAN_OPTIONS: FieldOption[] = [
  { value: "", label: "Unknown" },
  { value: "true", label: "Yes" },
  { value: "false", label: "No" },
]

export const EVENT_FIELD_GROUPS: { title: string; fields: EventField[] }[] = [
  {
    title: "Basics",
    fields: [
      { name: "title", label: "Title", kind: "text", required: true, maxLength: 160 },
      { name: "organizer", label: "Organizer", kind: "text", maxLength: 160 },
      { name: "summary", label: "Summary", kind: "textarea", requiredForReview: true, maxLength: 300 },
      { name: "description", label: "Description", kind: "textarea", maxLength: 5000 },
    ],
  },
  {
    title: "Classification",
    fields: [
      { name: "format", label: "Format", kind: "select", requiredForReview: true, options: FORMAT_OPTIONS },
      { name: "verification_status", label: "Verification", kind: "select", required: true, options: VERIFICATION_OPTIONS },
      { name: "categories", label: "Categories", kind: "tags", hint: "Comma-separated, e.g. ai, web3", placeholder: "ai, health" },
      { name: "technologies", label: "Technologies", kind: "tags", hint: "Comma-separated", placeholder: "python, react" },
    ],
  },
  {
    title: "Dates and place",
    fields: [
      { name: "start_date", label: "Start date", kind: "date", requiredForReview: true },
      { name: "end_date", label: "End date", kind: "date" },
      { name: "application_deadline", label: "Application deadline", kind: "date" },
      { name: "timezone", label: "Timezone", kind: "text", required: true, hint: "IANA name, e.g. Europe/Istanbul" },
      { name: "city", label: "City", kind: "text", maxLength: 120 },
      { name: "country", label: "Country", kind: "text", hint: "ISO 3166-1 alpha-2, e.g. TR", maxLength: 2 },
      { name: "venue", label: "Venue", kind: "text", maxLength: 200 },
    ],
  },
  {
    title: "Participation",
    fields: [
      { name: "eligibility", label: "Eligibility", kind: "textarea", maxLength: 500 },
      { name: "team_min", label: "Team size (min)", kind: "integer", hint: "1-20" },
      { name: "team_max", label: "Team size (max)", kind: "integer", hint: "1-20" },
      { name: "is_free", label: "Free to join", kind: "boolean", options: BOOLEAN_OPTIONS },
      { name: "prize_pool", label: "Prize pool", kind: "decimal", hint: "Requires a currency" },
      { name: "currency", label: "Currency", kind: "text", hint: "ISO 4217, e.g. TRY", maxLength: 3 },
    ],
  },
  {
    title: "Links",
    fields: [
      { name: "official_url", label: "Official URL", kind: "url", required: true, maxLength: 500 },
      { name: "application_url", label: "Application URL", kind: "url", maxLength: 500 },
      { name: "poster_url", label: "Poster URL", kind: "url", hint: "https only", maxLength: 500 },
      { name: "banner_url", label: "Banner URL", kind: "url", hint: "https only", maxLength: 500 },
      { name: "organizer_logo_url", label: "Organizer logo URL", kind: "url", hint: "https only", maxLength: 500 },
    ],
  },
  {
    title: "Internal",
    fields: [{ name: "internal_notes", label: "Internal notes", kind: "textarea", maxLength: 5000, hint: "Never shown publicly. Reject and request-changes reasons are appended here." }],
  },
]

export const EVENT_FIELDS: EventField[] = EVENT_FIELD_GROUPS.flatMap((group) => group.fields)

export const EMPTY_EVENT_VALUES: FormValues = {
  ...Object.fromEntries(EVENT_FIELDS.map((field) => [field.name, ""])),
  timezone: DEFAULT_TIMEZONE,
  verification_status: "unverified",
}

/** Form strings for an existing event (the edit form's initial values). */
export function eventToFormValues(event: Event): FormValues {
  const values: FormValues = {}
  for (const field of EVENT_FIELDS) {
    const value = event[field.name]
    if (value === null || value === undefined) values[field.name] = ""
    else if (Array.isArray(value)) values[field.name] = value.join(", ")
    else values[field.name] = String(value)
  }
  return values
}

/** Reads exactly the event fields from submitted form data. */
export function readEventForm(formData: FormData): FormValues {
  const values: FormValues = {}
  for (const field of EVENT_FIELDS) {
    const raw = formData.get(field.name)
    values[field.name] = typeof raw === "string" ? raw : ""
  }
  return values
}

/** Browsers submit textarea line breaks as CRLF; the API stores LF. */
export function normalizeText(value: string): string {
  return value.replace(/\r\n?/g, "\n").trim()
}

function parseTags(text: string): string[] {
  const tags = text
    .split(/[,\n]/)
    .map((tag) => tag.trim().toLowerCase())
    .filter(Boolean)
  return [...new Set(tags)]
}

const FORMATS: readonly EventFormat[] = ["in_person", "online", "hybrid"]
const VERIFICATIONS: readonly VerificationStatus[] = ["unverified", "partially_verified", "verified"]

function isOneOf<T extends string>(value: string, options: readonly T[]): value is T {
  return (options as readonly string[]).includes(value)
}

/**
 * Converts form strings to the API body. Every field is listed explicitly against the
 * generated `EventCreate` type, so a renamed or removed API field fails `tsc`. Empty
 * optional fields become null (clears them on PATCH); required text is sent as typed so
 * the API reports it per field.
 */
export function buildEventPayload(values: FormValues): {
  payload: EventCreate
  fieldErrors: Record<string, string>
} {
  const fieldErrors: Record<string, string> = {}
  const raw = (name: EventFieldName) => normalizeText(values[name] ?? "")
  const optional = (name: EventFieldName) => raw(name) || null
  const upper = (name: EventFieldName) => raw(name).toUpperCase() || null
  const integer = (name: EventFieldName) => {
    const text = raw(name)
    if (text === "") return null
    if (/^\d+$/.test(text)) return Number(text)
    fieldErrors[name] = "Enter a whole number."
    return null
  }
  const decimal = (name: EventFieldName) => {
    const text = raw(name)
    if (text === "") return null
    if (/^\d+(\.\d{1,2})?$/.test(text)) return text
    fieldErrors[name] = "Enter an amount such as 5000 or 5000.50."
    return null
  }
  const boolean = (name: EventFieldName) => (raw(name) === "" ? null : raw(name) === "true")

  const format = raw("format")
  if (format !== "" && !isOneOf(format, FORMATS)) fieldErrors.format = "Choose a format."
  const verification = raw("verification_status")
  if (!isOneOf(verification, VERIFICATIONS)) {
    fieldErrors.verification_status = "Choose a verification status."
  }

  const payload: EventCreate = {
    title: raw("title"),
    organizer: optional("organizer"),
    summary: optional("summary"),
    description: optional("description"),
    categories: parseTags(raw("categories")),
    technologies: parseTags(raw("technologies")),
    format: isOneOf(format, FORMATS) ? format : null,
    city: optional("city"),
    country: upper("country"),
    venue: optional("venue"),
    start_date: optional("start_date"),
    end_date: optional("end_date"),
    application_deadline: optional("application_deadline"),
    timezone: raw("timezone"),
    eligibility: optional("eligibility"),
    team_min: integer("team_min"),
    team_max: integer("team_max"),
    prize_pool: decimal("prize_pool"),
    currency: upper("currency"),
    is_free: boolean("is_free"),
    official_url: raw("official_url"),
    application_url: optional("application_url"),
    poster_url: optional("poster_url"),
    banner_url: optional("banner_url"),
    organizer_logo_url: optional("organizer_logo_url"),
    verification_status: isOneOf(verification, VERIFICATIONS) ? verification : "unverified",
    internal_notes: optional("internal_notes"),
  }
  return { payload, fieldErrors }
}

const NUMERIC = /^\d+(\.\d+)?$/

function sameValue(next: unknown, current: unknown): boolean {
  if (Array.isArray(next)) {
    return Array.isArray(current) && next.join("\u0000") === current.join("\u0000")
  }
  if (next === null || next === undefined || current === null || current === undefined) {
    return (next ?? null) === (current ?? null)
  }
  if (typeof next === "string" && typeof current === "string") {
    // prize_pool comes back as "5000.00" (Decimal) while the form may send "5000".
    if (NUMERIC.test(next) && NUMERIC.test(current)) return Number(next) === Number(current)
    return normalizeText(next) === normalizeText(current)
  }
  return next === current
}

/** Only the fields that differ from the current event (PATCH body). */
export function changedFields(payload: EventCreate, current: Event): EventUpdate {
  const changes: EventUpdate = {}
  const copy = <K extends EventFieldName>(key: K) => {
    if (!sameValue(payload[key], current[key])) changes[key] = payload[key]
  }
  for (const field of EVENT_FIELDS) copy(field.name)
  return changes
}

